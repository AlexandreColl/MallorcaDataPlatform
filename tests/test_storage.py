"""Buckets: created with versioning when missing, left alone when they exist (the pipeline role cannot change them)."""

import json
import re
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from core.storage import ensure_bucket


class _Buckets:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.calls: list[str] = []

    def head_bucket(self, Bucket):  # noqa: N803 - boto3 signature
        if Bucket not in self.existing:
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

    def create_bucket(self, Bucket):  # noqa: N803
        self.calls.append(f"create {Bucket}")
        self.existing.add(Bucket)

    def put_bucket_versioning(self, Bucket, VersioningConfiguration):  # noqa: N803
        self.calls.append(f"version {Bucket} {VersioningConfiguration['Status']}")


def test_a_missing_bucket_is_created_with_versioning():
    client = _Buckets(set())

    ensure_bucket(client, "bronze", versioned=True)

    assert client.calls == ["create bronze", "version bronze Enabled"]


def test_an_existing_bucket_is_not_touched():
    client = _Buckets({"bronze"})

    ensure_bucket(client, "bronze", versioned=True)

    assert client.calls == []


def test_a_denied_check_is_raised():
    class _Denied(_Buckets):
        def head_bucket(self, Bucket):  # noqa: N803
            raise ClientError({"Error": {"Code": "403"}}, "HeadBucket")

    with pytest.raises(ClientError):
        ensure_bucket(_Denied(set()), "bronze")


def test_the_local_pipeline_user_has_the_policy_of_the_aws_role():
    """docker/minio/pipeline-policy.json is the twin of the pipeline policy in infra/terraform/iam.tf."""
    root = Path(__file__).resolve().parents[1]
    local = json.loads((root / "docker" / "minio" / "pipeline-policy.json").read_text(encoding="utf-8"))
    terraform = (root / "infra" / "terraform" / "iam.tf").read_text(encoding="utf-8")
    pipeline = terraform.split('data "aws_iam_policy_document" "pipeline"')[1].split("\nresource ")[0]

    aws = {}
    for block in pipeline.split("statement {")[1:]:
        sid = re.search(r'sid\s*=\s*"(\w+)"', block).group(1)
        actions = re.search(r"actions\s*=\s*\[(.*?)\]", block, re.DOTALL).group(1)
        aws[sid] = set(re.findall(r'"([\w:]+)"', actions))

    assert {s["Sid"]: set(s["Action"]) for s in local["Statement"]} == aws
