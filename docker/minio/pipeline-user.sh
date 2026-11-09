#!/bin/sh
# Runs inside the minio container (make minio-pipeline-user). Creates the local twin of the AWS pipeline role: a
# user whose policy is the one of infra/terraform/iam.tf (list both lake buckets, read and write bronze without
# deleting, read, write and delete in silver). With S3_CREDENTIALS=role the pipeline assumes a role with this user's
# keys through MinIO's STS, and the temporary credentials carry this policy. Idempotent.
set -eu
mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc admin policy create local mdp-pipeline /tmp/pipeline-policy.json >/dev/null
mc admin user add local "$MINIO_PIPELINE_USER" "$MINIO_PIPELINE_PASSWORD" >/dev/null
mc admin policy attach local mdp-pipeline --user "$MINIO_PIPELINE_USER" >/dev/null 2>&1 || true  # already attached
echo "user $MINIO_PIPELINE_USER with policy mdp-pipeline"
