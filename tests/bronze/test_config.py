"""P5-D4: the Bronze a pod gets from its environment — dir by default, S3 with the chart's names."""

from __future__ import annotations

from pathlib import Path

import pytest

from energy_platform.bronze import FileBlobStore, S3BlobStore
from energy_platform.bronze.config import (
    BronzeConfigError,
    bronze_from_env,
    object_store_config,
    object_store_from_env,
    replica_bronze_from_env,
)
from tests.fetch.fake_s3 import FakeS3

S3_ENV = {
    "ENERGY_PLATFORM_BRONZE": "s3",
    "ENERGY_PLATFORM_S3_ENDPOINT": "http://minio.local:9000",
    "ENERGY_PLATFORM_S3_BUCKET": "bronze",
    "ENERGY_PLATFORM_S3_ALLOW_INSECURE": "true",
    "BRONZE_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
    "BRONZE_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
}


def test_default_is_a_directory(tmp_path: Path) -> None:
    bronze = bronze_from_env({"ENERGY_PLATFORM_BRONZE_DIR": str(tmp_path)})
    assert isinstance(bronze._hot, FileBlobStore)
    assert bronze_from_env({}) is not None  # ".bronze" fallback, nothing created yet


def test_s3_from_env_writes_through_the_fake_gateway() -> None:
    fake = FakeS3()
    bronze = bronze_from_env(S3_ENV, transport=fake.transport(), sleep=lambda _: None)
    assert isinstance(bronze._hot, S3BlobStore)
    sha = bronze._hot.put(b"payload")
    assert f"bronze/blobs/{sha[:2]}/{sha}" in fake.objects
    assert bronze._cold is None


def test_cold_store_is_optional_and_uses_its_own_secret() -> None:
    hot, cold = FakeS3(bucket="hot"), FakeS3(bucket="cold")
    env = {
        **S3_ENV,
        "ENERGY_PLATFORM_S3_COLD_ENDPOINT": "http://minio.local:9000",
        "ENERGY_PLATFORM_S3_COLD_BUCKET": "cold",
        "ENERGY_PLATFORM_S3_COLD_ALLOW_INSECURE": "1",
        "BRONZE_COLD_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "BRONZE_COLD_SECRET_ACCESS_KEY": "another",
    }
    bronze = bronze_from_env(env, transport=hot.transport(), sleep=lambda _: None)
    assert isinstance(bronze._cold, S3BlobStore)
    assert bronze._cold._store.bucket == "cold"
    del cold


def test_retention_and_allowed_hosts_are_parsed() -> None:
    env = {
        **S3_ENV,
        "ENERGY_PLATFORM_S3_RETENTION_MODE": "compliance",
        "ENERGY_PLATFORM_S3_RETENTION_DAYS": "90",
        "ENERGY_PLATFORM_S3_ALLOWED_HOSTS": "Minio.Local, other.example",
        "ENERGY_PLATFORM_S3_REGION": "eu-central",
    }
    config = object_store_config(env)
    assert config is not None
    assert config.retention is not None and config.retention.mode == "COMPLIANCE"
    assert config.retention.days == 90
    assert config.allowed_hosts == ("minio.local", "other.example")
    assert config.region == "eu-central" and config.allow_delete is False


def test_allowed_hosts_default_to_the_endpoint_host() -> None:
    config = object_store_config(
        {**S3_ENV, "ENERGY_PLATFORM_S3_ENDPOINT": "https://S3.Example:9443"}
    )
    assert config is not None and config.allowed_hosts == ("s3.example",)


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"ENERGY_PLATFORM_BRONZE": "swift"}, "dir|s3"),
        ({"ENERGY_PLATFORM_BRONZE": "s3"}, "ENERGY_PLATFORM_S3_ENDPOINT"),
        ({**S3_ENV, "ENERGY_PLATFORM_S3_BUCKET": ""}, "_BUCKET"),
        ({**S3_ENV, "ENERGY_PLATFORM_S3_RETENTION_MODE": "COMPLIANCE"}, "RETENTION"),
        ({**S3_ENV, "ENERGY_PLATFORM_S3_RETENTION_DAYS": "x"}, "RETENTION"),
    ],
)
def test_bad_environment_is_refused_with_the_variable_named(
    env: dict[str, str], fragment: str
) -> None:
    with pytest.raises(BronzeConfigError, match=fragment):
        bronze_from_env(env)


def test_missing_credentials_name_the_secret() -> None:
    env = {k: v for k, v in S3_ENV.items() if not k.startswith("BRONZE_")}
    with pytest.raises(LookupError, match="BRONZE"):
        object_store_from_env(env)


def test_replica_uses_its_own_prefix_and_secret() -> None:
    fake = FakeS3(bucket="replica")
    env = {
        "ENERGY_PLATFORM_S3_REPLICA_ENDPOINT": "http://minio.local:9000",
        "ENERGY_PLATFORM_S3_REPLICA_BUCKET": "replica",
        "ENERGY_PLATFORM_S3_REPLICA_ALLOW_INSECURE": "true",
        "BRONZE_REPLICA_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "BRONZE_REPLICA_SECRET_ACCESS_KEY": "s",
    }
    bronze = replica_bronze_from_env(env, transport=fake.transport(), sleep=lambda _: None)
    assert bronze.log.latest("ote_idm_soap") is None
    assert fake.calls()[0][0] == "GET"  # a listing, nothing written
