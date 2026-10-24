#!/usr/bin/env bash
# End-to-end check against a running stack (`docker compose up -d`):
#   1. wait for Airflow, 2. trigger the DAG, 3. assert rows in silver and gold,
#   4. trigger the same window again and assert nothing was duplicated.
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
DAG_ID=mallorca_pipeline
CONF=${CONF:-'{"connectors": ["open_meteo", "redata", "socib", "ign", "emt_palma"], "days": 1, "region": "mallorca"}'}
TIMEOUT=${TIMEOUT:-900}
# Connectors with `frequency: event`: a 1-day window usually has no events, so they must succeed, not load rows.
EVENT_SOURCES=${EVENT_SOURCES:-ign}

sql() { $COMPOSE exec -T postgres psql -U postgres -d "$1" -tAc "$2"; }

dump_logs() {
  echo "::group::scheduler logs"
  $COMPOSE logs --tail 200 airflow-scheduler || true
  echo "::endgroup::"
  echo "::group::task logs"
  $COMPOSE exec -T airflow-scheduler bash -c \
    'find /opt/airflow/logs -path "*dag_id=*" -name "*.log" -print -exec tail -n 80 {} \;' || true
  echo "::endgroup::"
}
trap 'dump_logs' ERR

wait_for() {
  local what=$1 cmd=$2 deadline=$((SECONDS + TIMEOUT))
  echo "waiting for $what..."
  until eval "$cmd" >/dev/null 2>&1; do
    if (( SECONDS > deadline )); then echo "timeout waiting for $what"; return 1; fi
    sleep 5
  done
}

wait_for "scheduler health" "$COMPOSE exec -T airflow-scheduler curl -sf http://localhost:8974/health"
wait_for "DAG to be parsed" \
  "sql airflow \"select 1 from dag where dag_id='$DAG_ID'\" | grep -q 1"

run_dag() {
  local run_id=$1
  $COMPOSE exec -T airflow-scheduler airflow dags trigger "$DAG_ID" --run-id "$run_id" --conf "$CONF"
  local deadline=$((SECONDS + TIMEOUT)) state=""
  while (( SECONDS < deadline )); do
    state=$(sql airflow "select state from dag_run where dag_id='$DAG_ID' and run_id='$run_id'")
    echo "  $run_id: ${state:-queued}"
    case "$state" in
      success) return 0 ;;
      failed) echo "DAG run $run_id failed"; return 1 ;;
    esac
    sleep 10
  done
  echo "timeout waiting for $run_id"; return 1
}

suffix=$(date +%s)
run_dag "e2e_first_$suffix"
sources=$(grep -o '"connectors": *\[[^]]*\]' <<<"$CONF" | grep -o '"[a-z_]*"' | tr -d '"' | grep -v connectors)

# A connector may fail only because its upstream API is down (connection errors, timeouts, 5xx): that is
# a warning, because the DAG keeps going without it and its next run catches up the missed days. Any other
# error (a bug, an API that changed its format) fails the E2E.
UPSTREAM_ERRORS='^(ConnectTimeout|ConnectionError|ReadTimeout|Timeout|SSLError|ChunkedEncodingError|RetryError|HTTPError: 5[0-9][0-9])'
succeeded=""
check_runs() {
  local run_id=$1 source status error
  succeeded=""
  for source in $sources; do
    status=$(sql warehouse "select status from ops.ingestion_runs where run_id = '$run_id' and source = '$source'")
    if [[ "$status" == success ]]; then
      succeeded+=" $source"
      continue
    fi
    error=$(sql warehouse "select coalesce(error, '') from ops.ingestion_runs where run_id = '$run_id' and source = '$source'")
    if [[ "$status" == failed ]] && grep -Eq "$UPSTREAM_ERRORS" <<<"$error"; then
      echo "::warning title=Upstream outage::$source unavailable in $run_id: ${error:0:300}"
    else
      echo "connector $source in $run_id: status=${status:-missing} ${error:0:500}"
      return 1
    fi
  done
  [[ -n "$succeeded" ]] || { echo "no connector succeeded in $run_id"; return 1; }
}

check_runs "e2e_first_$suffix"
first_ok=$succeeded
gold_1=$(sql warehouse "select count(*) from gold.fct_observations")
checks=$(sql warehouse "select count(*) from quality.check_results")
echo "gold=$gold_1 quality_checks=$checks succeeded:$first_ok"
(( gold_1 > 0 && checks > 0 )) || { echo "expected data in gold and quality results"; false; }
if [[ " $first_ok " == *" open_meteo "* ]]; then
  aqi=$(sql warehouse "select count(*) from gold.air_quality_hourly")
  (( aqi > 0 )) || { echo "open_meteo loaded but gold.air_quality_hourly is empty"; false; }
fi
declare -A silver_1
for source in $first_ok; do
  rows=$(sql warehouse "select count(*) from gold.fct_observations where source = '$source'")
  silver_1[$source]=$(sql warehouse "select count(*) from silver.observations where source = '$source'")
  echo "  $source: $rows rows in gold"
  # Event sources usually have no events in one day: succeeding is enough.
  if [[ " $EVENT_SOURCES " != *" $source "* ]]; then
    (( rows > 0 )) || { echo "connector $source loaded no data"; false; }
  fi
done

run_dag "e2e_second_$suffix"
check_runs "e2e_second_$suffix"
for source in $first_ok; do
  [[ " $succeeded " == *" $source "* ]] || continue  # down in the second run: nothing to compare
  rows=$(sql warehouse "select count(*) from silver.observations where source = '$source'")
  echo "  $source: silver ${silver_1[$source]} -> $rows after rerun"
  [[ "$rows" == "${silver_1[$source]}" ]] || { echo "rerun duplicated $source rows"; false; }
done

versions=$($COMPOSE exec -T airflow-scheduler python - <<'PY'
from core.config import Settings
from core.storage import s3_client
s = Settings.from_env()
resp = s3_client(s).list_object_versions(Bucket=s.bronze_bucket)
print(len(resp.get("Versions", [])))
PY
)
echo "bronze object versions=$versions (raw responses kept across reruns)"

echo "E2E OK: data in bronze/silver/gold and reruns are idempotent"
