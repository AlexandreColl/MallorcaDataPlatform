# Read-only REST API over the gold layer (FastAPI + uvicorn). Small image: no Airflow, Spark or Java.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 api
WORKDIR /app

COPY requirements/api.txt /tmp/requirements-api.txt
RUN pip install -r /tmp/requirements-api.txt

COPY api/ /app/api/
USER api

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health', timeout=4)"
CMD ["uvicorn", "--factory", "api.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
