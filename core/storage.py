"""Bronze layer: raw payloads in S3-compatible object storage (MinIO locally, S3 on AWS)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from botocore.config import Config
from botocore.exceptions import ClientError

from core.credentials import boto3_session
from core.models import RawPayload

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mypy_boto3_s3 import S3Client
    from mypy_boto3_s3.type_defs import ListObjectsV2OutputTypeDef

    from core.config import Settings

log = logging.getLogger(__name__)


def s3_client(settings: Settings, name: str = "mdp-bronze") -> S3Client:
    """S3 client with path-style addressing, which MinIO requires, and the credentials of ``S3_CREDENTIALS``."""
    return boto3_session(settings, name).client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 10}),
    )


def ensure_bucket(client: S3Client, bucket: str, *, versioned: bool = False) -> None:
    """Create the bucket if it does not exist, with versioning when asked.

    An existing bucket is left as it is: on AWS Terraform creates and configures it, and the pipeline role may only
    read and write objects (no ``s3:PutBucketVersioning``, no ``s3:CreateBucket``).
    """
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    else:
        return
    log.info("creating bucket %s", bucket)
    client.create_bucket(Bucket=bucket)
    if versioned:
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})


class BronzeStore:
    """Raw API responses. Keys are deterministic; versioning keeps every past response."""

    def __init__(self, settings: Settings, client: S3Client | None = None) -> None:
        self.bucket = settings.bronze_bucket
        self.client = client or s3_client(settings)

    def ensure(self) -> None:
        """Create the bronze bucket with versioning enabled."""
        ensure_bucket(self.client, self.bucket, versioned=True)

    def put(self, payload: RawPayload, key: str | None = None) -> str:
        """Store a payload under its deterministic key (or ``key``, a live snapshot's) and return the key."""
        key = key or payload.key
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload.to_json().encode("utf-8"),
            ContentType="application/json",
        )
        log.info("bronze <- s3://%s/%s", self.bucket, key)
        return key

    def get(self, key: str) -> RawPayload:
        """Read the latest version of a payload."""
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return RawPayload.from_json(obj["Body"].read())

    def keys(self, prefix: str) -> list[str]:
        """Every key under ``prefix``, in order."""
        return sorted(item for page in self._pages(prefix) for item in (o["Key"] for o in page.get("Contents", [])))

    def folders(self, prefix: str) -> list[str]:
        """The next level of ``prefix`` (``day=2026-11-26/``...), in order, without listing the objects inside."""
        found = (p["Prefix"] for page in self._pages(prefix, delimiter="/") for p in page.get("CommonPrefixes", []))
        return sorted(found)

    def _pages(self, prefix: str, delimiter: str | None = None) -> Iterator[ListObjectsV2OutputTypeDef]:
        paginator = self.client.get_paginator("list_objects_v2")
        if delimiter:
            yield from paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter=delimiter)
        else:
            yield from paginator.paginate(Bucket=self.bucket, Prefix=prefix)
