"""Credentials for the object store, shared by bronze (boto3) and Spark (S3A).

Three modes, chosen with ``S3_CREDENTIALS``:

- ``static`` (default): fixed keys, ``S3_ACCESS_KEY`` and ``S3_SECRET_KEY``. MinIO with its local user.
- ``role``: assume the role ``S3_ROLE_ARN`` through STS and use its temporary credentials, renewed before they expire.
  The base identity that assumes it is the static keys when they are set, or the SDK's default chain. This is the
  trust model of ``infra/terraform/iam.tf`` (the account assumes ``<prefix>-pipeline``), and MinIO's STS
  (``S3_STS_ENDPOINT_URL=http://minio:9000``) runs the same flow locally.
- ``default``: the SDK's default chain (environment, profile, web identity, ECS task role, EC2 instance profile): no
  keys in the configuration at all, as on a machine that already runs with the role.

Both clients get the same mode, so bronze and silver are written with the same identity.
"""

from __future__ import annotations

import re
from datetime import UTC
from typing import TYPE_CHECKING

import boto3
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session

if TYPE_CHECKING:
    from core.config import Settings

MODES = ("static", "role", "default")
_MIN_SESSION_NAME = 2  # STS accepts 2 to 64 characters
_MAX_SESSION_NAME = 64

# Spark's S3A providers for each mode (hadoop-aws 3.5 with the AWS SDK v2).
_SIMPLE = "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
_ASSUMED_ROLE = "org.apache.hadoop.fs.s3a.auth.AssumedRoleCredentialProvider"
_DEFAULT_CHAIN = "software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider"


class CredentialsConfigError(ValueError):
    """``S3_CREDENTIALS`` names an unknown mode, or a role without its ARN."""


def check(settings: Settings) -> None:
    """Fail early, with the variable to set, on an unknown mode or a role without its ARN."""
    if settings.s3_credentials not in MODES:
        msg = f"S3_CREDENTIALS must be one of {', '.join(MODES)}, not '{settings.s3_credentials}'"
        raise CredentialsConfigError(msg)
    if settings.s3_credentials == "role" and not settings.s3_role_arn:
        msg = "S3_CREDENTIALS=role needs S3_ROLE_ARN (terraform output pipeline_env gives it)"
        raise CredentialsConfigError(msg)


def session_name(name: str) -> str:
    """An STS session name from an app name: letters, digits and ``_+=,.@-``, 2 to 64 characters (CloudTrail)."""
    cleaned = re.sub(r"[^\w+=,.@-]", "-", name)[:_MAX_SESSION_NAME]
    return cleaned if len(cleaned) >= _MIN_SESSION_NAME else "mdp"


def _has_static_keys(settings: Settings) -> bool:
    return bool(settings.s3_access_key and settings.s3_secret_key)


def _static_kwargs(settings: Settings) -> dict[str, str]:
    return {"aws_access_key_id": settings.s3_access_key, "aws_secret_access_key": settings.s3_secret_key}


def _sts_client(settings: Settings):  # noqa: ANN202 - a botocore STS client
    """STS with the base identity: the static keys when they are set, else the SDK's default chain."""
    base = boto3.Session(
        **(_static_kwargs(settings) if _has_static_keys(settings) else {}), region_name=settings.s3_region
    )
    return base.client("sts", endpoint_url=settings.s3_sts_endpoint_url or None)


def boto3_session(settings: Settings, name: str = "mdp") -> boto3.Session:
    """A boto3 session with the credentials of the configured mode."""
    check(settings)
    if settings.s3_credentials == "static":
        return boto3.Session(**_static_kwargs(settings), region_name=settings.s3_region)
    if settings.s3_credentials == "default":
        return boto3.Session(region_name=settings.s3_region)

    sts = _sts_client(settings)

    def assume() -> dict[str, str]:
        creds = sts.assume_role(
            RoleArn=settings.s3_role_arn,
            RoleSessionName=session_name(name),
            DurationSeconds=settings.s3_role_session_seconds,
        )["Credentials"]
        expiry = creds["Expiration"]
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return {
            "access_key": creds["AccessKeyId"],
            "secret_key": creds["SecretAccessKey"],
            "token": creds["SessionToken"],
            "expiry_time": expiry.astimezone(UTC).isoformat(),
        }

    # botocore renews them shortly before they expire, so a backfill longer than the session keeps working.
    credentials = RefreshableCredentials.create_from_metadata(
        metadata=assume(), refresh_using=assume, method="sts-assume-role"
    )
    botocore_session = get_session()
    botocore_session._credentials = credentials  # noqa: SLF001 - the documented way to plug refreshable credentials
    botocore_session.set_config_variable("region", settings.s3_region)
    return boto3.Session(botocore_session=botocore_session)


def spark_s3a_config(settings: Settings, name: str = "mdp") -> dict[str, str]:
    """The ``spark.hadoop.fs.s3a.*`` credential settings of the configured mode."""
    check(settings)
    prefix = "spark.hadoop.fs.s3a."
    if settings.s3_credentials == "default":
        return {f"{prefix}aws.credentials.provider": _DEFAULT_CHAIN}
    keys = (
        {f"{prefix}access.key": settings.s3_access_key, f"{prefix}secret.key": settings.s3_secret_key}
        if _has_static_keys(settings)
        else {}
    )
    if settings.s3_credentials == "static":
        return {**keys, f"{prefix}aws.credentials.provider": _SIMPLE}
    # S3A assumes the role itself and renews the session before it expires, like boto3 above.
    config = {
        **keys,
        f"{prefix}aws.credentials.provider": _ASSUMED_ROLE,
        f"{prefix}assumed.role.arn": settings.s3_role_arn,
        f"{prefix}assumed.role.session.name": session_name(name),
        f"{prefix}assumed.role.session.duration": f"{settings.s3_role_session_seconds}s",
        f"{prefix}assumed.role.credentials.provider": _SIMPLE if keys else _DEFAULT_CHAIN,
        f"{prefix}assumed.role.sts.endpoint.region": settings.s3_region,
    }
    if settings.s3_sts_endpoint_url:
        config[f"{prefix}assumed.role.sts.endpoint"] = settings.s3_sts_endpoint_url
    return config
