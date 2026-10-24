-- Warehouse DDL. Idempotent: safe to run on every pipeline start.

CREATE SCHEMA IF NOT EXISTS landing;   -- per-run staging tables written by Spark (JDBC)
CREATE SCHEMA IF NOT EXISTS silver;    -- clean observations, common schema
CREATE SCHEMA IF NOT EXISTS quality;   -- data-quality check results
CREATE SCHEMA IF NOT EXISTS ops;       -- pipeline audit
CREATE SCHEMA IF NOT EXISTS gold;      -- dbt models

CREATE TABLE IF NOT EXISTS silver.observations (
    source           text             NOT NULL,
    entity           text             NOT NULL,
    metric           text             NOT NULL,
    ts               timestamptz      NOT NULL,
    value            double precision,
    unit             text             NOT NULL,
    quality          text             NOT NULL CHECK (quality IN ('ok', 'suspect', 'missing')),
    quality_reasons  text,
    lat              double precision,
    lon              double precision,
    run_id           text             NOT NULL,
    ingested_at      timestamptz      NOT NULL,
    updated_at       timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (source, entity, metric, ts)
);

CREATE INDEX IF NOT EXISTS ix_observations_metric_ts ON silver.observations (metric, ts);

CREATE TABLE IF NOT EXISTS quality.check_results (
    run_id        text        NOT NULL,
    source        text        NOT NULL,
    rule          text        NOT NULL,
    target        text        NOT NULL,
    checked       bigint      NOT NULL,
    failed        bigint      NOT NULL,
    passed        boolean     NOT NULL,
    details       text,
    window_start  date        NOT NULL,
    window_end    date        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, source, rule, target)
);

CREATE TABLE IF NOT EXISTS ops.ingestion_runs (
    run_id         text        NOT NULL,
    source         text        NOT NULL,
    region         text        NOT NULL,
    window_start   date        NOT NULL,
    window_end     date        NOT NULL,
    status         text        NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    payloads       integer,
    rows_silver    integer,
    rows_upserted  integer,
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    error          text,
    PRIMARY KEY (run_id, source)
);
