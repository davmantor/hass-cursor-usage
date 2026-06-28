from __future__ import annotations

import base64
import importlib.util
import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


AUTH_MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "hass_cursor_usage" / "auth.py"


def load_auth_module():
    spec = importlib.util.spec_from_file_location("hass_cursor_usage_auth", AUTH_MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


auth = load_auth_module()


def jwt_with_payload(payload: dict[str, object]) -> str:
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    return ".".join(
        (
            encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()),
            encode(json.dumps(payload).encode()),
            encode(b"signature"),
        )
    )


def test_constants_match_cursor_contract() -> None:
    assert auth.CURSOR_OAUTH_CLIENT_ID == "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"
    assert auth.ACCESS_TOKEN_REFRESH_WINDOW == timedelta(minutes=5)


def test_read_auth_file_uses_top_level_tokens_and_preserves_unknown_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    data = {
        "access_token": "access",
        "refresh_token": "refresh",
        "id_token": "identity",
        "future_cursor_field": {"keep": True},
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = auth.read_auth_file(path)

    assert loaded.data == data
    assert loaded.access_token == "access"
    assert loaded.refresh_token == "refresh"


def test_read_auth_file_accepts_camel_case_keys(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"accessToken":"access-c","refreshToken":"refresh-c"}', encoding="utf-8")

    loaded = auth.read_auth_file(path)

    assert loaded.access_token == "access-c"
    assert loaded.refresh_token == "refresh-c"


def test_read_auth_file_prefers_snake_case_over_camel_case(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(
        '{"access_token":"snake","refresh_token":"snake-r","accessToken":"camel","refreshToken":"camel-r"}',
        encoding="utf-8",
    )

    loaded = auth.read_auth_file(path)

    assert loaded.access_token == "snake"
    assert loaded.refresh_token == "snake-r"


def test_read_auth_file_expands_user_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"access_token":"a","refresh_token":"r"}', encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    assert auth.read_auth_file("~/auth.json").access_token == "a"


@pytest.mark.parametrize("contents", ["{not-json", "[]", '"string"', "null"])
def test_read_auth_file_rejects_malformed_or_non_object_json_safely(
    tmp_path: Path, contents: str
) -> None:
    path = tmp_path / "auth.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(auth.AuthFileError) as raised:
        auth.read_auth_file(path)

    assert contents not in str(raised.value)


def test_read_auth_file_reports_missing_file_without_exposing_path_contents(
    tmp_path: Path,
) -> None:
    secret = "literal-secret-in-filename"
    path = tmp_path / secret

    with pytest.raises(auth.AuthFileError) as raised:
        auth.read_auth_file(path)

    assert secret not in str(raised.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token", ""),
        ("access_token", 123),
        ("refresh_token", "   "),
        ("refresh_token", None),
    ],
)
def test_read_auth_file_extracts_only_nonempty_string_tokens(
    tmp_path: Path, field: str, value: object
) -> None:
    data: dict[str, object] = {"access_token": "a", "refresh_token": "r"}
    data[field] = value
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = auth.read_auth_file(path)

    assert getattr(loaded, field) is None


def test_access_token_refreshes_when_missing_expired_or_at_window() -> None:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)

    assert auth.access_token_needs_refresh(None, now=now)
    assert auth.access_token_needs_refresh(
        jwt_with_payload({"exp": (now - timedelta(seconds=1)).timestamp()}), now=now
    )
    assert auth.access_token_needs_refresh(
        jwt_with_payload({"exp": (now + timedelta(minutes=5)).timestamp()}), now=now
    )


def test_access_token_remains_fresh_outside_window_with_naive_now() -> None:
    now = datetime(2026, 6, 13, 12, 0)
    token = jwt_with_payload({"exp": int(datetime(2026, 6, 13, 12, 6, tzinfo=UTC).timestamp())})

    assert not auth.access_token_needs_refresh(token, now=now)


@pytest.mark.parametrize(
    "token",
    ["not-a-jwt", "one.two.three", jwt_with_payload({"exp": "tomorrow"})],
)
def test_access_token_refreshes_for_malformed_jwt_or_exp(token: str) -> None:
    assert auth.access_token_needs_refresh(token)


def test_access_token_without_exp_may_remain_usable() -> None:
    assert not auth.access_token_needs_refresh(jwt_with_payload({"sub": "user"}))


def test_build_refresh_request_is_exact() -> None:
    assert auth.build_refresh_request("refresh-token") == {
        "client_id": "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB",
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token",
    }


def test_apply_refreshed_tokens_merges_nonempty_top_level_values() -> None:
    original = {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "id_token": "old-id",
        "unknown": [1, 2],
    }
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)

    merged = dict(original)
    access_token = auth.apply_refreshed_tokens(
        merged,
        {"access_token": "new-access", "refresh_token": "", "id_token": None},
        now=now,
    )

    assert merged == {
        "access_token": "new-access",
        "refresh_token": "old-refresh",
        "id_token": "old-id",
        "unknown": [1, 2],
        "last_refresh": "2026-06-13T12:00:00+00:00",
    }
    assert access_token == "new-access"
    assert original["access_token"] == "old-access"


def test_apply_refreshed_tokens_returns_none_for_no_valid_access_token() -> None:
    merged: dict[str, object] = {}
    token = auth.apply_refreshed_tokens(merged, {"access_token": 42})

    assert token is None
    assert "access_token" not in merged


def test_persist_refreshed_tokens_writes_and_returns_access_token(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text('{"access_token":"old","refresh_token":"refresh"}', encoding="utf-8")

    token = auth.persist_refreshed_tokens(
        path, json.loads(path.read_text()), {"access_token": "new"}
    )

    assert token == "new"
    assert json.loads(path.read_text())["access_token"] == "new"


def test_persist_refreshed_tokens_requires_resulting_access_token(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"

    with pytest.raises(auth.RefreshTokenResponseError):
        auth.persist_refreshed_tokens(path, {"refresh_token": "refresh"}, {})

    assert not path.exists()


def test_atomic_write_preserves_existing_mode(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o600)

    auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_persist_refreshed_tokens_clamps_world_readable_file_to_0600(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    data = {"access_token": "old", "refresh_token": "refresh"}
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o644)

    auth.persist_refreshed_tokens(path, data, {"access_token": "new"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_atomic_write_preserves_owner_read_only_mode(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o400)

    auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o400


def test_atomic_write_clamps_group_readable_mode_to_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o640)

    auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_atomic_write_new_file_is_restrictive(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"

    auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def test_atomic_write_cleans_up_tempfile_on_replace_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "auth.json"

    def fail_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(auth.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert list(tmp_path.iterdir()) == []


def test_atomic_write_cleans_up_tempfile_on_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "auth.json"

    def interrupt_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(auth.os, "replace", interrupt_replace)

    with pytest.raises(KeyboardInterrupt):
        auth.write_auth_file_atomically(path, {"access_token": "new"})

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (400, {"error": {"code": "refresh_token_expired"}}, "refresh_token_expired"),
        (400, {"error": "refresh_token_reused"}, "refresh_token_reused"),
        (400, {"code": "refresh_token_invalidated"}, "refresh_token_invalidated"),
        (400, {"error": "invalid_grant"}, "invalid_grant"),
        (401, {"message": "unauthorized"}, None),
    ],
)
def test_refresh_rejection_classifies_permanent_failures(
    status: int, body: dict[str, object], code: str | None
) -> None:
    rejection = auth.refresh_rejection_from_response(status, json.dumps(body))

    assert isinstance(rejection, auth.RefreshTokenRejectedError)
    assert rejection.code == code


@pytest.mark.parametrize(
    ("status", "body"),
    [(500, {"error": "temporary"}), (429, {"error": "rate_limited"}), (400, {"error": "other"})],
)
def test_refresh_rejection_treats_other_failures_as_transient(
    status: int, body: dict[str, object]
) -> None:
    assert auth.refresh_rejection_from_response(status, json.dumps(body)) is None


def test_refresh_rejection_treats_known_code_on_server_error_as_transient() -> None:
    body = json.dumps({"error": "invalid_grant"})

    assert auth.refresh_rejection_from_response(500, body) is None


def test_refresh_rejection_never_exposes_response_or_token_literal() -> None:
    secret = "supplied-secret-token-literal"

    rejection = auth.refresh_rejection_from_response(
        401, json.dumps({"error": {"code": "refresh_token_expired"}, "token": secret})
    )

    assert rejection is not None
    assert secret not in str(rejection)


def test_derive_session_cookie_uses_suffix_of_workos_subject() -> None:
    token = jwt_with_payload({"sub": "google-oauth2|user-123"})

    cookie = auth.derive_session_cookie(token)

    from urllib.parse import quote

    assert cookie == f"WorkosCursorSessionToken={quote(f'user-123::{token}', safe='')}"


def test_derive_session_cookie_uses_entire_plain_subject() -> None:
    token = jwt_with_payload({"sub": "plain-user"})

    cookie = auth.derive_session_cookie(token)

    from urllib.parse import quote

    assert cookie == f"WorkosCursorSessionToken={quote(f'plain-user::{token}', safe='')}"


def test_derive_session_cookie_keeps_subject_suffix_after_first_delimiter() -> None:
    token = jwt_with_payload({"sub": "provider|tenant|user-123"})

    cookie = auth.derive_session_cookie(token)

    from urllib.parse import quote

    assert cookie == f"WorkosCursorSessionToken={quote(f'tenant|user-123::{token}', safe='')}"


def test_derive_session_cookie_rejects_whitespace_only_subject_suffix_safely() -> None:
    token = jwt_with_payload({"sub": "provider|   "})

    with pytest.raises(auth.AuthFileError) as raised:
        auth.derive_session_cookie(token)

    assert token not in str(raised.value)


@pytest.mark.parametrize("payload", [{}, {"sub": ""}, {"sub": "provider|"}, {"sub": 12}])
def test_derive_session_cookie_rejects_missing_or_empty_subject_safely(
    payload: dict[str, object],
) -> None:
    token = jwt_with_payload(payload)

    with pytest.raises(auth.AuthFileError) as raised:
        auth.derive_session_cookie(token)

    assert token not in str(raised.value)
