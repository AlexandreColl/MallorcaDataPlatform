#!/bin/bash
# Runs once, when the postgres volume is created.
# Creates the Airflow metadata DB, the warehouse DB and a read-only role for Grafana.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v airflow_pw="$AIRFLOW_DB_PASSWORD" \
  -v warehouse_user="$WAREHOUSE_USER" \
  -v warehouse_pw="$WAREHOUSE_PASSWORD" \
  -v warehouse_db="$WAREHOUSE_DB" \
  -v grafana_user="$GRAFANA_DB_USER" \
  -v grafana_pw="$GRAFANA_DB_PASSWORD" <<-'EOSQL'
	CREATE ROLE airflow LOGIN PASSWORD :'airflow_pw';
	CREATE DATABASE airflow OWNER airflow;

	CREATE ROLE :"warehouse_user" LOGIN PASSWORD :'warehouse_pw';
	CREATE DATABASE :"warehouse_db" OWNER :"warehouse_user";

	CREATE ROLE :"grafana_user" LOGIN PASSWORD :'grafana_pw';
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$WAREHOUSE_DB" \
  -v warehouse_user="$WAREHOUSE_USER" \
  -v grafana_user="$GRAFANA_DB_USER" <<-'EOSQL'
	CREATE SCHEMA landing AUTHORIZATION :"warehouse_user";
	CREATE SCHEMA silver  AUTHORIZATION :"warehouse_user";
	CREATE SCHEMA quality AUTHORIZATION :"warehouse_user";
	CREATE SCHEMA ops     AUTHORIZATION :"warehouse_user";
	CREATE SCHEMA gold    AUTHORIZATION :"warehouse_user";

	GRANT USAGE ON SCHEMA silver, quality, ops, gold TO :"grafana_user";
	ALTER DEFAULT PRIVILEGES FOR ROLE :"warehouse_user" IN SCHEMA silver, quality, ops, gold
	  GRANT SELECT ON TABLES TO :"grafana_user";
EOSQL
