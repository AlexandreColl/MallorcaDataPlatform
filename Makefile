# Mallorca Data Platform - developer commands.
# Usage examples:
#   make up
#   make run CONNECTORS=open_meteo DAYS=30
#   make run-local CONNECTORS=open_meteo DAYS=1

SHELL := /bin/bash
COMPOSE ?= docker compose
CONNECTORS ?= open_meteo
DAYS ?= 1
REGION ?= mallorca

comma := ,
empty :=
space := $(empty) $(empty)
CONNECTORS_JSON := [$(patsubst %,"%",$(subst $(comma),$(space),$(CONNECTORS)))]
CONNECTORS_JSON := $(subst $(space),$(comma),$(CONNECTORS_JSON))
RUN_CONF := {"connectors": $(CONNECTORS_JSON), "days": $(DAYS), "region": "$(REGION)"}

.DEFAULT_GOAL := help
.PHONY: help init build up down clean ps logs run run-local connectors test lint format dbt dbt-full-refresh psql e2e

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

init: ## Create .env from .env.example (if missing)
	@test -f .env || (cp .env.example .env && echo "created .env")

build: init ## Build the Airflow/Spark/dbt image
	$(COMPOSE) build

up: init ## Start the whole platform
	$(COMPOSE) up -d --build
	@echo "Airflow  http://localhost:8080"
	@echo "Grafana  http://localhost:3000"
	@echo "MinIO    http://localhost:9001"

down: ## Stop the platform (keeps data)
	$(COMPOSE) down

clean: ## Stop and delete all data volumes
	$(COMPOSE) down -v --remove-orphans

ps: ## Service status
	$(COMPOSE) ps

logs: ## Follow logs (SERVICE=airflow-scheduler to filter)
	$(COMPOSE) logs -f $(SERVICE)

run: ## Trigger the Airflow DAG: make run CONNECTORS=open_meteo,redata DAYS=30
	$(COMPOSE) exec airflow-scheduler airflow dags trigger mallorca_pipeline --conf '$(RUN_CONF)'

run-local: ## Run the pipeline without Airflow (CLI inside the image)
	$(COMPOSE) exec airflow-scheduler python -m core.cli run --connectors $(subst $(comma),$(space),$(CONNECTORS)) --days $(DAYS) --region $(REGION)

connectors: ## List available connectors and regions
	$(COMPOSE) exec airflow-scheduler python -m core.cli list

test: ## Run unit tests (+ DAG integrity) inside the dev image
	$(COMPOSE) --profile tools run --rm toolbox pytest

lint: ## Lint and format check, report only (same as CI)
	$(COMPOSE) --profile tools run --rm toolbox bash -c "ruff check --no-fix . && ruff format --check ."

format: ## Apply ruff fixes (including unsafe ones) and format
	$(COMPOSE) --profile tools run --rm toolbox bash -c "ruff check . && ruff format ."

DBT = cd /opt/project/dbt && /opt/dbt-venv/bin/dbt
DBT_ARGS = --profiles-dir . --target-path /tmp/dbt/target --log-path /tmp/dbt/logs

dbt: ## Run dbt source freshness (warnings only) and dbt build against the warehouse
	$(COMPOSE) exec airflow-scheduler bash -c "($(DBT) source freshness $(DBT_ARGS) || true) && $(DBT) build $(DBT_ARGS)"

dbt-full-refresh: ## Rebuild every dbt model from scratch (incremental ones included)
	$(COMPOSE) exec airflow-scheduler bash -c "$(DBT) build --full-refresh $(DBT_ARGS)"

psql: ## Open psql on the warehouse
	$(COMPOSE) exec postgres psql -U postgres -d warehouse

e2e: ## End-to-end check (same as CI): run twice and assert idempotency
	./scripts/e2e.sh
