"""Cursor authentication-file and token helpers."""

from __future__ import annotations

import base64
import binascii
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

CURSOR_OAUTH_CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"
ACCESS_TOKEN_REFRESH_WINDOW = timedelta(minutes=5)

_TOKEN_FIELDS = ("id_token", "access_token", "refresh_token")
_PERMANENT_REFRESH_ERROR_CODES = {
    "refresh_token_expired",
    "refresh_token_reused",
    "refresh_token_invalidated",
    "invalid_grant",
}
_UTC = UTC


class AuthFileError(Exception):
    """Raised when Cursor credentials cannot be safely read or interpreted."""


class RefreshTokenRejectedError(Exception):
    """Raised when Cursor permanently rejects a refresh token."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class RefreshTokenResponseError(Exception):
    """Raised when a refresh response does not contain usable credentials."""


@dataclass(frozen=True, slots=True)
class CursorAuthFile:
    """Cursor credential data and its extracted bearer tokens."""

    data: dict[str, Any]
    access_token: str | None
    refresh_token: str | None


def read_auth_file(auth_file: str | os.PathLike[str]) -> CursorAuthFile:
    """Read top-level tokens from a Cursor credential JSON object."""
    path = Path(auth_file).expanduser()
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except OSError as err:
        raise AuthFileError("Unable to read the Cursor auth file") from err
    except (json.JSONDecodeError, UnicodeError) as err:
        raise AuthFileError("Cursor auth file contains malformed JSON") from err

    if not isinstance(data, dict):
        raise AuthFileError("Cursor auth file must contain a JSON object")

    return CursorAuthFile(
        data=data,
        access_token=_nonempty_string(data.get("access_token")) or _nonempty_string(data.get("accessToken")),
        refresh_token=_nonempty_string(data.get("refresh_token")) or _nonempty_string(data.get("refreshToken")),
    )


def access_token_needs_refresh(
    access_token: str | None,
    *,
    now: datetime | None = None,
    refresh_window: timedelta = ACCESS_TOKEN_REFRESH_WINDOW,
) -> bool:
    """Return whether a JWT is unusable, expired, or within the refresh window."""
    if not _nonempty_string(access_token):
        return True

    current_time = now or datetime.now(_UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=_UTC)
    else:
        current_time = current_time.astimezone(_UTC)

    try:
        expires_at = _jwt_expiration(access_token)
    except (OverflowError, OSError, ValueError):
        return True

    return expires_at is not None and expires_at <= current_time + refresh_window


def build_refresh_request(refresh_token: str) -> dict[str, str]:
    """Build the exact Cursor OAuth refresh request body."""
    return {
        "client_id": CURSOR_OAUTH_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }


def apply_refreshed_tokens(
    auth_data: dict[str, Any],
    refresh_response: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str | None:
    """Merge usable returned tokens into the top-level auth data."""
    for field in _TOKEN_FIELDS:
        value = _nonempty_string(refresh_response.get(field))
        if value is not None:
            auth_data[field] = value

    refreshed_at = now or datetime.now(_UTC)
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=_UTC)
    auth_data["last_refresh"] = refreshed_at.astimezone(_UTC).isoformat()

    return _nonempty_string(auth_data.get("access_token"))


def persist_refreshed_tokens(
    auth_file: str | os.PathLike[str],
    auth_data: dict[str, Any],
    refresh_response: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str:
    """Merge, validate, and atomically persist refreshed credentials."""
    access_token = apply_refreshed_tokens(auth_data, refresh_response, now=now)
    if access_token is None:
        raise RefreshTokenResponseError(
            "Cursor token refresh did not produce a usable access token"
        )
    write_auth_file_atomically(auth_file, auth_data)
    return access_token


def write_auth_file_atomically(
    auth_file: str | os.PathLike[str], auth_data: dict[str, Any]
) -> None:
    """Atomically replace an auth file through a restrictive sibling tempfile."""
    path = Path(auth_file).expanduser()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None
    try:
        owner_mode = stat.S_IMODE(path.stat().st_mode) & 0o600
        existing_mode = owner_mode or 0o600
    except FileNotFoundError:
        existing_mode = None
    except OSError as err:
        raise AuthFileError("Unable to inspect the Cursor auth file") from err

    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        if existing_mode is not None:
            os.chmod(temporary_path, existing_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            fd = -1
            json.dump(auth_data, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def refresh_rejection_from_response(status: int, body: str) -> RefreshTokenRejectedError | None:
    """Classify only permanent refresh-token rejections without echoing the body."""
    code = _extract_refresh_error_code(body)
    normalized_code = code.lower() if code is not None else None
    if status in (400, 401) and normalized_code in _PERMANENT_REFRESH_ERROR_CODES:
        return RefreshTokenRejectedError(
            "Cursor permanently rejected the refresh token; sign in again", code
        )
    if status == 401:
        return RefreshTokenRejectedError("Cursor rejected the refresh token; sign in again", code)
    return None


def derive_session_cookie(access_token: str) -> str:
    """Derive Cursor's WorkOS session cookie from an access-token subject."""
    try:
        subject = _decode_jwt_payload(access_token).get("sub")
    except ValueError as err:
        raise AuthFileError("Unable to derive a Cursor session from the access token") from err

    if not isinstance(subject, str) or not subject.strip():
        raise AuthFileError("Cursor access token has no usable subject")
    user_id = subject.split("|", 1)[-1].strip()
    if not user_id:
        raise AuthFileError("Cursor access token has no usable subject")

    encoded = quote(f"{user_id}::{access_token}", safe="")
    return f"WorkosCursorSessionToken={encoded}"


def _jwt_expiration(token: str) -> datetime | None:
    exp = _decode_jwt_payload(token).get("exp")
    if exp is None:
        return None
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        raise ValueError("JWT exp claim is not numeric")
    return datetime.fromtimestamp(exp, _UTC)


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    if not isinstance(token, str):
        raise ValueError("Invalid JWT format")
    parts = token.split(".")
    if len(parts) != 3 or not parts[0] or not parts[1]:
        raise ValueError("Invalid JWT format")

    encoded_payload = parts[1]
    encoded_payload += "=" * (-len(encoded_payload) % 4)
    try:
        raw_payload = base64.b64decode(encoded_payload, altchars=b"-_", validate=True)
        claims = json.loads(raw_payload.decode("utf-8"))
    except (binascii.Error, UnicodeError, json.JSONDecodeError, ValueError) as err:
        raise ValueError("Invalid JWT payload") from err
    if not isinstance(claims, dict):
        raise ValueError("JWT payload must be a JSON object")
    return claims


def _extract_refresh_error_code(body: str) -> str | None:
    try:
        decoded = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None

    error = decoded.get("error")
    if isinstance(error, dict):
        return _nonempty_string(error.get("code"))
    if isinstance(error, str):
        return _nonempty_string(error)
    return _nonempty_string(decoded.get("code"))


def _nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
