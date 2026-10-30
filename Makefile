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
.PHONY: help init build up down clean ps logs run run-local connectors test lint format dbt dbt-full-refresh psql e2e detect evaluate backfill api-role api-test screenshots tf-check tf-fmt

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
	@echo "API      http://localhost:8000/docs"

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

detect: ## Flag anomalies in the recent silver values: make detect DAYS=30 (at least rescore_days)
	$(COMPOSE) exec airflow-scheduler python -m core.cli detect --days $(DAYS)

backfill: ## Load a past date range, one run per year: make backfill CONNECTORS=aemet START=2016-09-01 END=2026-08-31
	$(COMPOSE) exec airflow-scheduler python -m core.cli backfill --connectors $(subst $(comma),$(space),$(CONNECTORS)) --start $(START) --end $(END) --region $(REGION)

api-role: ## Create or update the read-only API role on an existing postgres volume (idempotent)
	$(COMPOSE) exec -T postgres bash /docker-entrypoint-initdb.d/02-api-reader.sh

api-test: ## Unit tests of the REST API (no database needed)
	$(COMPOSE) run --rm toolbox pytest api

evaluate: ## Measure the anomaly detectors against injected faults (precision and recall)
	$(COMPOSE) exec airflow-scheduler python -m core.cli evaluate

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

# Terraform and tflint run in their official images: nothing to install, and no AWS account or credentials needed.
TF_DIR = $(CURDIR)/infra/terraform
TERRAFORM = docker run --rm -v "$(TF_DIR)":/tf -w /tf -v mdp-tf-plugins:/plugins -e TF_PLUGIN_CACHE_DIR=/plugins \
	hashicorp/terraform:1.16.6
TFLINT = docker run --rm -v "$(TF_DIR)":/data -w /data -v mdp-tflint-plugins:/plugins -e TFLINT_PLUGIN_DIR=/plugins \
	ghcr.io/terraform-linters/tflint:v0.64.0

tf-check: ## Terraform fmt, validate, tflint and tests against a mocked AWS (no account, no cost; same as CI)
	$(TERRAFORM) fmt -check -recursive
	$(TERRAFORM) init -backend=false -input=false
	$(TERRAFORM) validate
	$(TFLINT) --init
	$(TFLINT) --recursive
	$(TERRAFORM) test

tf-fmt: ## Format the Terraform files
	$(TERRAFORM) fmt -recursive

screenshots: ## Screenshot every Grafana dashboard into docs/img (Playwright in Docker, stack running)
	docker run --rm --network host -v "$(CURDIR)":/work -w /work mcr.microsoft.com/playwright/python:v1.55.0-noble \
		bash -c "pip install -q playwright==1.55.0 && python scripts/grafana_screenshots.py docs/img"

e2e: ## End-to-end check (same as CI): run twice and assert idempotency
	./scripts/e2e.sh
