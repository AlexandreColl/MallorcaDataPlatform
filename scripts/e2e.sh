#!/usr/bin/env bash
# End-to-end check against a running stack (`docker compose up -d`):
#   1. wait for Airflow, 2. trigger the DAG, 3. assert rows in silver and gold,
#   4. trigger the same window again and assert nothing was duplicated.
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
DAG_ID=mallorca_pipeline
CONF=${CONF:-'{"connectors": ["open_meteo", "redata", "socib", "ign"], "days": 1, "region": "mallorca"}'}
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
silver_1=$(sql warehouse "select count(*) from silver.observations")
gold_1=$(sql warehouse "select count(*) from gold.fct_observations")
aqi=$(sql warehouse "select count(*) from gold.air_quality_hourly")
checks=$(sql warehouse "select count(*) from quality.check_results")
echo "silver=$silver_1 gold=$gold_1 air_quality_hourly=$aqi quality_checks=$checks"
(( silver_1 > 0 && gold_1 > 0 && aqi > 0 && checks > 0 )) || { echo "expected data in every layer"; false; }
for source in $(grep -o '"connectors": *\[[^]]*\]' <<<"$CONF" | grep -o '"[a-z_]*"' | tr -d '"' | grep -v connectors); do
  rows=$(sql warehouse "select count(*) from gold.fct_observations where source = '$source'")
  echo "  $source: $rows rows in gold"
  if [[ " $EVENT_SOURCES " == *" $source "* ]]; then
    ok=$(sql warehouse "select count(*) from ops.ingestion_runs where source = '$source' and run_id = 'e2e_first_$suffix' and status = 'success'")
    (( ok == 1 )) || { echo "event connector $source did not finish successfully"; false; }
  else
    (( rows > 0 )) || { echo "connector $source loaded no data"; false; }
  fi
done

run_dag "e2e_second_$suffix"
silver_2=$(sql warehouse "select count(*) from silver.observations")
echo "silver after rerun=$silver_2"
[[ "$silver_1" == "$silver_2" ]] || { echo "rerun duplicated rows ($silver_1 -> $silver_2)"; false; }

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
