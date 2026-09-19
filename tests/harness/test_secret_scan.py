"""F10: the placeholder exemption applies to the matched value, not the whole line.

Fake credentials are assembled at runtime so that this file never contains one.
"""

from __future__ import annotations

from scripts.secret_scan import scan_text

FAKE_GH = "ghp_" + "A" * 36
FAKE_AWS = "AKIA" + "Q" * 16


def test_bare_token_is_reported() -> None:
    assert scan_text("f", f"token = {FAKE_GH}\n") == ["f:1: github token"]


def test_token_next_to_example_comment_is_still_reported() -> None:
    # The reviewer's probe P02: whole-line exemption used to hide this.
    assert scan_text("f", f"token = {FAKE_GH}  # example\n") == ["f:1: github token"]


def test_token_inside_example_url_is_still_reported() -> None:
    assert scan_text("f", f"https://example.org/{FAKE_GH}\n") == ["f:1: github token"]


def test_aws_key_id_reported_once_per_line() -> None:
    assert scan_text("f", f"a={FAKE_AWS} b={FAKE_AWS}\n") == ["f:1: AWS access key id"]


def test_placeholder_values_pass() -> None:
    text = "\n".join(
        [
            "password = REPLACE-WITH-YOUR-PASSWORD-VALUE",
            "api_key = ${OTE_API_KEY_PLACEHOLDER}",
            "secret_key: <redacted-secret-value>",
            "Authorization: Bearer example-token-goes-here-value",
            "access_token = xxxxxxxxxxxxxxxxxxxxxxxx",
        ]
    )
    assert scan_text("f", text) == []


def test_explicit_allow_marker_is_a_reviewed_exception() -> None:
    assert scan_text("f", f"fixture = {FAKE_GH}  # secret-scan:allow synthetic\n") == []


def test_real_looking_password_is_reported() -> None:
    line = "password = " + "hunter2" * 3 + "\n"  # assembled so this file never contains it
    assert scan_text("f", line) == ["f:1: generic assignment"]
