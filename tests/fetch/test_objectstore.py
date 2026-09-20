"""The S3 client on the fake gateway: SigV4 KAT, verbs, headers, allowlist, pagination, retries."""

from __future__ import annotations

import base64
import hashlib
import random
from datetime import UTC, datetime
from typing import Any

import pytest

from energy_platform.fetch.client import RetryPolicy
from energy_platform.fetch.objectstore import (
    EMPTY_SHA256,
    Credentials,
    ObjectStore,
    ObjectStoreConfig,
    ObjectStoreError,
    Retention,
    check_endpoint,
    sign_v4,
)
from tests.fetch.fake_s3 import FakeS3

# AWS documentation example ("Signature Calculations for the Authorization Header: Transferring
# Payload in a Single Chunk", GET object).
AK = "AKIAIOSFODNN7EXAMPLE"
SK = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AT = datetime(2013, 5, 24, 0, 0, 0, tzinfo=UTC)
CREDS = Credentials(AK, SK)
NOW = datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC)


def config(**kw: Any) -> ObjectStoreConfig:
    defaults: dict[str, Any] = {
        "endpoint": "http://minio.local:9000",
        "bucket": "bronze",
        "allowed_hosts": ("minio.local",),
        "allow_insecure": True,
    }
    return ObjectStoreConfig(**{**defaults, **kw})


def store(fake: FakeS3, **kw: Any) -> ObjectStore:
    slept: list[float] = kw.pop("slept", [])
    return ObjectStore(
        config(**kw.pop("config", {})),
        CREDS,
        transport=fake.transport(),
        clock=lambda: NOW,
        sleep=slept.append,
        rng=random.SystemRandom(),
        **kw,
    )


# ------------------------------------------------------------------ signing


def test_sigv4_known_answer_from_the_aws_documentation() -> None:
    signed = sign_v4(
        method="GET",
        url="https://examplebucket.s3.amazonaws.com/test.txt",
        headers={"Range": "bytes=0-9"},
        payload_sha256=EMPTY_SHA256,
        credentials=CREDS,
        region="us-east-1",
        at=AT,
    )
    assert signed.canonical_request == "\n".join(
        [
            "GET",
            "/test.txt",
            "",
            "host:examplebucket.s3.amazonaws.com",
            "range:bytes=0-9",
            f"x-amz-content-sha256:{EMPTY_SHA256}",
            "x-amz-date:20130524T000000Z",
            "",
            "host;range;x-amz-content-sha256;x-amz-date",
            EMPTY_SHA256,
        ]
    )
    assert signed.string_to_sign == "\n".join(
        [
            "AWS4-HMAC-SHA256",
            "20130524T000000Z",
            "20130524/us-east-1/s3/aws4_request",
            "7344ae5b7ee6c3e7e6b0fe0640412a37625d1fbfff95c48bbb2dc43964946972",
        ]
    )
    assert signed.signature == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    assert signed.headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


def test_sigv4_sorts_the_query_and_signs_the_session_token() -> None:
    signed = sign_v4(
        method="GET",
        url="https://s3.example.org/bronze?prefix=captures%2Ft&list-type=2&max-keys=2",
        headers={},
        payload_sha256=EMPTY_SHA256,
        credentials=Credentials(AK, SK, session_token="tok"),
        region="eu-central-1",
        at=AT,
    )
    lines = signed.canonical_request.split("\n")
    assert lines[1:3] == ["/bronze", "list-type=2&max-keys=2&prefix=captures%2Ft"]
    assert "x-amz-security-token:tok" in lines
    assert signed.headers["x-amz-security-token"] == "tok"
    assert "eu-central-1/s3/aws4_request" in signed.headers["authorization"]


def test_credentials_hide_the_secret_in_repr_and_come_from_env() -> None:
    env = {
        "BRONZE_HOT_ACCESS_KEY_ID": AK,
        "BRONZE_HOT_SECRET_ACCESS_KEY": SK,
        "BRONZE_HOT_SESSION_TOKEN": "tok",
    }
    creds = Credentials.from_env("bronze-hot", env)
    assert (creds.access_key_id, creds.secret_access_key, creds.session_token) == (AK, SK, "tok")
    assert SK not in repr(creds) and "tok" not in repr(creds)
    no_token = {k: v for k, v in env.items() if "SESSION" not in k}
    without = Credentials.from_env("bronze-hot", no_token)
    assert without.session_token is None
    with pytest.raises(LookupError, match="BRONZE_HOT_SECRET_ACCESS_KEY"):
        Credentials.from_env("bronze-hot", {"BRONZE_HOT_ACCESS_KEY_ID": AK})


# ------------------------------------------------------------------ endpoint policy


@pytest.mark.parametrize(
    ("endpoint", "allowed", "insecure", "code"),
    [
        ("https://s3.example.org", ("other.example.org",), False, "endpoint_not_allowed"),
        ("http://minio.local:9000", ("minio.local",), False, "insecure_endpoint"),
        ("ftp://minio.local", ("minio.local",), True, "insecure_endpoint"),
        ("https://user:pw@s3.example.org", ("s3.example.org",), False, "endpoint_not_allowed"),
        ("https://s3.example.org/bucket", ("s3.example.org",), False, "endpoint_not_allowed"),
        ("https://s3.example.org?x=1", ("s3.example.org",), False, "endpoint_not_allowed"),
        ("https:///nohost", (), False, "endpoint_not_allowed"),
    ],
)
def test_endpoint_is_refused_before_any_request(
    endpoint: str, allowed: tuple[str, ...], insecure: bool, code: str
) -> None:
    fake = FakeS3()
    with pytest.raises(ObjectStoreError) as err:
        ObjectStore(
            config(endpoint=endpoint, allowed_hosts=allowed, allow_insecure=insecure),
            CREDS,
            transport=fake.transport(),
        )
    assert err.value.code == code and fake.requests == []


def test_endpoint_normalises_case_and_default_port() -> None:
    assert check_endpoint("https://S3.Example.org:443/", ("s3.example.org",), False) == (
        "https://s3.example.org"
    )
    assert check_endpoint("http://minio:9000", ("minio",), True) == "http://minio:9000"
    assert check_endpoint("http://127.0.0.1:9000", ("127.0.0.1",), True) == "http://127.0.0.1:9000"


# ------------------------------------------------------------------ verbs


def test_put_is_path_style_with_content_hash_md5_and_type() -> None:
    fake = FakeS3()
    s = store(fake)
    etag = s.put("bronze/blobs/ab/abcd", b"payload", content_type="text/xml")
    (req,) = fake.requests
    assert (
        req.method == "PUT"
        and str(req.url) == "http://minio.local:9000/bronze/bronze/blobs/ab/abcd"
    )
    assert req.headers["x-amz-content-sha256"] == hashlib.sha256(b"payload").hexdigest()
    assert (
        req.headers["content-md5"]
        == base64.b64encode(hashlib.md5(b"payload", usedforsecurity=False).digest()).decode()
    )
    assert req.headers["content-type"] == "text/xml"
    assert "x-amz-object-lock-mode" not in req.headers
    assert etag == fake.objects["bronze/blobs/ab/abcd"].etag
    signed = req.headers["authorization"]
    assert "content-md5" in signed and "content-type" in signed


def test_put_sends_object_lock_headers_from_the_configured_retention() -> None:
    fake = FakeS3()
    s = store(fake, config={"retention": Retention("COMPLIANCE", 30)})
    s.put("k", b"x")
    (req,) = fake.requests
    assert req.headers["x-amz-object-lock-mode"] == "COMPLIANCE"
    assert req.headers["x-amz-object-lock-retain-until-date"] == "2026-10-20T10:00:00Z"
    assert fake.objects["k"].retain_until == "2026-10-20T10:00:00Z"
    with pytest.raises(ValueError, match=">= 1"):
        Retention("GOVERNANCE", 0)


def test_keys_are_uri_encoded_once_and_the_signature_covers_the_encoded_path() -> None:
    fake = FakeS3()
    s = store(fake)
    s.put("captures/t/2026/09/20/2026-09-20T100000Z_1.json", b"{}")
    s.put("odd key/with space+plus", b"1")
    assert fake.calls()[1] == ("PUT", "/bronze/odd%20key/with%20space%2Bplus")
    assert s.get("odd key/with space+plus") == b"1"


def test_get_and_head_return_none_on_404_and_data_otherwise() -> None:
    fake = FakeS3()
    s = store(fake)
    assert s.get("missing") is None
    assert s.head("missing") is None
    s.put("present", b"abc", content_type="application/json")
    assert s.get("present") == b"abc"
    info = s.head("present")
    assert info is not None
    assert (info.key, info.size, info.content_type) == ("present", 3, "application/json")
    assert info.etag == fake.objects["present"].etag
    assert [c[0] for c in fake.calls()] == ["GET", "HEAD", "PUT", "GET", "HEAD"]


def test_list_follows_continuation_tokens_across_pages() -> None:
    fake = FakeS3()
    s = store(fake)
    for i in range(7):
        s.put(f"captures/t/{i:02d}.json", b"{}")
    s.put("captures/u/00.json", b"{}")
    fake.requests.clear()
    got = list(s.list("captures/t/", page_size=3))
    assert [o.key for o in got] == [f"captures/t/{i:02d}.json" for i in range(7)]
    assert all(o.size == 2 and o.etag for o in got)
    calls = fake.calls()
    assert len(calls) == 3
    assert calls[0] == ("GET", "/bronze?list-type=2&max-keys=3&prefix=captures%2Ft%2F")
    assert "continuation-token=captures%2Ft%2F02.json" in calls[1][1]
    assert "continuation-token=captures%2Ft%2F05.json" in calls[2][1]
    assert list(s.list("captures/none/")) == []


def test_delete_is_refused_without_the_flag_and_works_with_it() -> None:
    fake = FakeS3()
    s = store(fake)
    s.put("k", b"x")
    with pytest.raises(ObjectStoreError) as err:
        s.delete("k")
    assert err.value.code == "delete_not_allowed" and "k" in fake.objects
    assert [c[0] for c in fake.calls()] == ["PUT"]
    tiering = store(fake, config={"allow_delete": True})
    tiering.delete("k")
    assert "k" not in fake.objects and fake.calls()[-1] == ("DELETE", "/bronze/k")


# ------------------------------------------------------------------ failures


def test_5xx_and_connection_errors_are_retried_then_raised_with_the_s3_code() -> None:
    fake = FakeS3(faults=[503, None, 500])
    slept: list[float] = []
    s = store(fake, slept=slept, retry=RetryPolicy(attempts=4, base_seconds=0.5))
    s.put("k", b"x")
    assert len(fake.requests) == 4 and len(slept) == 3 and "k" in fake.objects

    fake = FakeS3(faults=[500, 500])
    s = store(fake, retry=RetryPolicy(attempts=2))
    with pytest.raises(ObjectStoreError) as err:
        s.get("k")
    assert err.value.code == "InternalError" and len(fake.requests) == 2


def test_4xx_is_not_retried_and_carries_the_s3_error_code() -> None:
    fake = FakeS3(faults=[403])
    s = store(fake)
    with pytest.raises(ObjectStoreError) as err:
        s.put("k", b"x")
    assert err.value.code == "InternalError" and len(fake.requests) == 1  # fake's code for 403 too
    assert SK not in str(err.value)


def test_a_real_transport_is_stopped_by_the_unit_test_socket_block() -> None:
    s = ObjectStore(
        config(endpoint="https://s3.example.org", allowed_hosts=("s3.example.org",)),
        CREDS,
        sleep=lambda _: None,
        retry=RetryPolicy(attempts=1),
    )
    with pytest.raises(RuntimeError, match="network disabled in unit tests"):
        s.get("k")
    s.close()


def test_bad_keys_are_refused_locally() -> None:
    fake = FakeS3()
    s = store(fake)
    for key in ("", "/leading"):
        with pytest.raises(ObjectStoreError, match="bad_key"):
            s.get(key)
    assert fake.requests == []
