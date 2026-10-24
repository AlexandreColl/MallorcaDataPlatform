"""Bronze layer: raw payloads in S3-compatible object storage (MinIO locally, S3 on AWS)."""

from __future__ import annotations

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from core.config import Settings
from core.models import RawPayload

log = logging.getLogger(__name__)


def s3_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 10}),
    )


def ensure_bucket(client, bucket: str, versioned: bool = False) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket", "NotFound"):
            raise
        log.info("creating bucket %s", bucket)
        client.create_bucket(Bucket=bucket)
    if versioned:
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})


class BronzeStore:
    """Raw API responses. Keys are deterministic; versioning keeps every past response."""

    def __init__(self, settings: Settings, client=None) -> None:
        self.bucket = settings.bronze_bucket
        self.client = client or s3_client(settings)

    def ensure(self) -> None:
        ensure_bucket(self.client, self.bucket, versioned=True)

    def put(self, payload: RawPayload) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=payload.key,
            Body=payload.to_json().encode("utf-8"),
            ContentType="application/json",
        )
        log.info("bronze <- s3://%s/%s", self.bucket, payload.key)
        return payload.key

    def get(self, key: str) -> RawPayload:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return RawPayload.from_json(obj["Body"].read())
