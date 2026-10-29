#!/bin/bash
# Read-only role of the REST API: the gold marts and silver (for the anomaly flags), never write access.
# Runs when the postgres volume is created; on an existing volume run `make api-role` (idempotent).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$WAREHOUSE_DB" \
  -v warehouse_user="$WAREHOUSE_USER" \
  -v warehouse_db="$WAREHOUSE_DB" \
  -v api_user="$API_DB_USER" \
  -v api_pw="$API_DB_PASSWORD" <<-'EOSQL'
	SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'api_user', :'api_pw')
	WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'api_user') \gexec
	ALTER ROLE :"api_user" SET default_transaction_read_only = on;

	GRANT CONNECT ON DATABASE :"warehouse_db" TO :"api_user";
	GRANT USAGE ON SCHEMA gold, silver TO :"api_user";
	GRANT SELECT ON ALL TABLES IN SCHEMA gold, silver TO :"api_user";
	-- dbt drops and recreates the marts, and silver.anomalies is created later by `core.cli init`:
	-- tables the warehouse role creates from now on are readable too.
	ALTER DEFAULT PRIVILEGES FOR ROLE :"warehouse_user" IN SCHEMA gold, silver GRANT SELECT ON TABLES TO :"api_user";
EOSQL
