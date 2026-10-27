# Airflow + PySpark (local mode) + dbt in an isolated venv.
ARG AIRFLOW_VERSION=3.3.2
ARG PYTHON_VERSION=3.14

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION} AS runtime
ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
# Versions matching the Hadoop client bundled with PySpark 4.2 (Hadoop 3.5.0).
ARG HADOOP_AWS_VERSION=3.5.0
ARG AWS_SDK_V2_VERSION=2.35.4
# Compile dependency of hadoop-aws >= 3.5.0 (S3 Analytics Accelerator input stream).
ARG S3_ANALYTICS_ACCELERATOR_VERSION=1.3.1
ARG POSTGRES_JDBC_VERSION=42.7.14
ARG DBT_POSTGRES_VERSION=1.11.0
# Pinned: dbt-postgres accepts dbt-core>=1.8.0rc1, and that pre-release marker lets pip pick dbt-core betas.
ARG DBT_CORE_VERSION=1.12.6

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless curl \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/default-java

# Spark jars for S3A (MinIO/S3) and JDBC (PostgreSQL).
RUN mkdir -p /opt/spark-jars \
 && curl -fsSL -o /opt/spark-jars/hadoop-aws.jar \
    "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" \
 && curl -fsSL -o /opt/spark-jars/aws-sdk-bundle.jar \
    "https://repo1.maven.org/maven2/software/amazon/awssdk/bundle/${AWS_SDK_V2_VERSION}/bundle-${AWS_SDK_V2_VERSION}.jar" \
 && curl -fsSL -o /opt/spark-jars/s3-analytics-accelerator.jar \
    "https://repo1.maven.org/maven2/software/amazon/s3/analyticsaccelerator/analyticsaccelerator-s3/${S3_ANALYTICS_ACCELERATOR_VERSION}/analyticsaccelerator-s3-${S3_ANALYTICS_ACCELERATOR_VERSION}.jar" \
 && curl -fsSL -o /opt/spark-jars/postgresql.jar \
    "https://repo1.maven.org/maven2/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar"
ENV SPARK_EXTRA_JARS=/opt/spark-jars/hadoop-aws.jar,/opt/spark-jars/aws-sdk-bundle.jar,/opt/spark-jars/s3-analytics-accelerator.jar,/opt/spark-jars/postgresql.jar

# dbt lives in its own venv so its dependencies never clash with Airflow's.
RUN python -m venv /opt/dbt-venv \
 && /opt/dbt-venv/bin/pip install --no-cache-dir "dbt-core==${DBT_CORE_VERSION}" "dbt-postgres==${DBT_POSTGRES_VERSION}" \
 && chown -R airflow:0 /opt/dbt-venv \
 && mkdir -p /opt/dbt \
 && chown airflow:0 /opt/dbt

USER airflow
COPY requirements/runtime.txt /tmp/requirements-runtime.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements-runtime.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

ENV MDP_PROJECT_ROOT=/opt/project \
    PYTHONPATH=/opt/project \
    AIRFLOW__CORE__DAGS_FOLDER=/opt/project/dags

# Project code is baked in for releases; docker-compose mounts it over for development.
COPY --chown=airflow:0 core /opt/project/core
COPY --chown=airflow:0 connectors /opt/project/connectors
COPY --chown=airflow:0 config /opt/project/config
COPY --chown=airflow:0 dbt /opt/project/dbt
# dbt packages (dbt/package-lock.yml) are installed outside the project: compose mounts the checkout read-only
# over /opt/project, so they could not be installed there at run time.
# dbt deps deletes and recreates the folder, so it must sit in a directory the airflow user owns.
ENV DBT_PACKAGES_INSTALL_PATH=/opt/dbt/packages
RUN cd /opt/project/dbt && /opt/dbt-venv/bin/dbt deps --log-path /tmp/dbt-deps-logs && rm -rf /tmp/dbt-deps-logs
COPY --chown=airflow:0 dags /opt/project/dags

# Dev image: adds test/lint tooling (used by `make test` and `make lint`).
FROM runtime AS dev
ARG RUFF_VERSION=0.17.2
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" pytest pytest-cov "ruff==${RUFF_VERSION}" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
