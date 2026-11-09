"""Credentials of the object store: static keys, an assumed role (STS) or the SDK's default chain."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from core import credentials


@dataclass(frozen=True)
class _Settings:
    s3_credentials: str = "static"
    s3_access_key: str = "user"
    s3_secret_key: str = "secret"  # noqa: S105 - a fake
    s3_region: str = "eu-south-2"
    s3_role_arn: str = ""
    s3_sts_endpoint_url: str = ""
    s3_role_session_seconds: int = 3600


ROLE = _Settings(s3_credentials="role", s3_role_arn="arn:aws:iam::123456789012:role/mdp-pipeline")


class _FakeSts:
    """STS that hands out numbered sessions, expiring ``lifetime`` from now."""

    def __init__(self, lifetime: timedelta) -> None:
        self.lifetime = lifetime
        self.calls: list[dict] = []

    def assume_role(self, **kwargs):
        self.calls.append(kwargs)
        n = len(self.calls)
        return {
            "Credentials": {
                "AccessKeyId": f"ASIA{n}",
                "SecretAccessKey": f"secret{n}",
                "SessionToken": f"token{n}",
                "Expiration": datetime.now(UTC) + self.lifetime,
            }
        }


def test_static_keys_for_boto3_and_spark():
    frozen = credentials.boto3_session(_Settings()).get_credentials().get_frozen_credentials()
    spark = credentials.spark_s3a_config(_Settings())

    assert (frozen.access_key, frozen.secret_key, frozen.token) == ("user", "secret", None)
    assert spark == {
        "spark.hadoop.fs.s3a.access.key": "user",
        "spark.hadoop.fs.s3a.secret.key": "secret",
        "spark.hadoop.fs.s3a.aws.credentials.provider": "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    }


def test_default_chain_carries_no_keys(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "from-env")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
    settings = _Settings(s3_credentials="default")

    frozen = credentials.boto3_session(settings).get_credentials().get_frozen_credentials()
    spark = credentials.spark_s3a_config(settings)

    assert frozen.access_key == "from-env"
    assert spark == {"spark.hadoop.fs.s3a.aws.credentials.provider": credentials._DEFAULT_CHAIN}


def test_role_gives_boto3_the_temporary_credentials(monkeypatch):
    sts = _FakeSts(timedelta(hours=1))
    monkeypatch.setattr(credentials, "_sts_client", lambda settings: sts)

    frozen = credentials.boto3_session(ROLE, "mdp-open_meteo").get_credentials().get_frozen_credentials()

    assert (frozen.access_key, frozen.secret_key, frozen.token) == ("ASIA1", "secret1", "token1")
    assert sts.calls == [{"RoleArn": ROLE.s3_role_arn, "RoleSessionName": "mdp-open_meteo", "DurationSeconds": 3600}]


def test_role_renews_the_session_before_it_expires(monkeypatch):
    sts = _FakeSts(timedelta(seconds=30))  # inside botocore's refresh margin
    monkeypatch.setattr(credentials, "_sts_client", lambda settings: sts)
    session_credentials = credentials.boto3_session(ROLE).get_credentials()

    renewed = session_credentials.get_frozen_credentials()

    assert len(sts.calls) == 2
    assert renewed.token == "token2"  # noqa: S105 - a fake


def test_role_for_spark_assumes_it_with_the_base_keys():
    settings = replace(ROLE, s3_sts_endpoint_url="http://minio:9000", s3_role_session_seconds=900)

    spark = credentials.spark_s3a_config(settings, "mdp anomalies")

    assert spark["spark.hadoop.fs.s3a.aws.credentials.provider"] == (
        "org.apache.hadoop.fs.s3a.auth.AssumedRoleCredentialProvider"
    )
    assert spark["spark.hadoop.fs.s3a.assumed.role.arn"] == ROLE.s3_role_arn
    assert spark["spark.hadoop.fs.s3a.assumed.role.session.name"] == "mdp-anomalies"
    assert spark["spark.hadoop.fs.s3a.assumed.role.session.duration"] == "900s"
    assert spark["spark.hadoop.fs.s3a.assumed.role.sts.endpoint"] == "http://minio:9000"
    assert spark["spark.hadoop.fs.s3a.assumed.role.sts.endpoint.region"] == "eu-south-2"
    assert spark["spark.hadoop.fs.s3a.assumed.role.credentials.provider"] == (
        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
    )
    assert spark["spark.hadoop.fs.s3a.access.key"] == "user"


def test_role_without_keys_assumes_it_from_the_default_chain():
    spark = credentials.spark_s3a_config(replace(ROLE, s3_access_key="", s3_secret_key=""))

    assert "spark.hadoop.fs.s3a.access.key" not in spark
    assert "spark.hadoop.fs.s3a.assumed.role.sts.endpoint" not in spark  # AWS's own STS
    assert spark["spark.hadoop.fs.s3a.assumed.role.credentials.provider"] == (
        "software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider"
    )


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (_Settings(s3_credentials="sso"), "S3_CREDENTIALS must be one of static, role, default"),
        (_Settings(s3_credentials="role"), "S3_CREDENTIALS=role needs S3_ROLE_ARN"),
    ],
)
def test_a_wrong_mode_fails_early(settings, message):
    with pytest.raises(ValueError, match=message):
        credentials.spark_s3a_config(settings)
    with pytest.raises(ValueError, match=message):
        credentials.boto3_session(settings)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("mdp-open_meteo", "mdp-open_meteo"), ("mdp anomalies/2", "mdp-anomalies-2"), ("x", "mdp"), ("a" * 80, "a" * 64)],
)
def test_session_name_follows_sts_rules(name, expected):
    assert credentials.session_name(name) == expected
