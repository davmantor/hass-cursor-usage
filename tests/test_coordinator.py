from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

try:
    import homeassistant  # noqa: F401
except ImportError:
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class ConfigEntry:
        def __class_getitem__(cls, _item: object) -> type[ConfigEntry]:
            return cls

    class ConfigEntryAuthFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, _item: object) -> type[DataUpdateCoordinator]:
            return cls

        def __init__(self, hass: object, _logger: object, **kwargs: object) -> None:
            self.hass = hass
            self.config_entry = kwargs.get("config_entry")
            self.update_interval = kwargs.get("update_interval")

    class UpdateFailed(Exception):
        pass

    class Platform:
        SENSOR = "sensor"

    config_entries.ConfigEntry = ConfigEntry
    const.Platform = Platform
    core.HomeAssistant = object
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    aiohttp_client.async_get_clientsession = lambda hass: hass.session
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    helpers.aiohttp_client = aiohttp_client
    homeassistant.config_entries = config_entries
    homeassistant.const = const
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.const": const,
            "homeassistant.core": core,
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.aiohttp_client": aiohttp_client,
            "homeassistant.helpers.update_coordinator": update_coordinator,
        }
    )

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

import custom_components.hass_cursor_usage as coordinator_module
from custom_components.hass_cursor_usage import (
    CursorUsageCoordinator,
    UsageUnauthorized,
    _async_fetch_usage,
    _async_request_token_refresh,
)
from custom_components.hass_cursor_usage.auth import CursorAuthFile, RefreshTokenRejectedError
from custom_components.hass_cursor_usage.const import (
    CONF_AUTH_FILE,
    TOKEN_REFRESH_URL,
    USAGE_API_URL,
)


class FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        json_data: object = None,
        text: str = "",
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text = text
        self._json_error = json_error

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    async def text(self) -> str:
        return self._text


class FakeSession:
    def __init__(
        self,
        *,
        gets: list[FakeResponse] | None = None,
        posts: list[FakeResponse] | None = None,
    ):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append((url, kwargs))
        return self.gets.pop(0)

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append((url, kwargs))
        return self.posts.pop(0)


def _auth(access: str | None = "access", refresh: str | None = "refresh") -> CursorAuthFile:
    return CursorAuthFile(
        data={"access_token": access, "refresh_token": refresh},
        access_token=access,
        refresh_token=refresh,
    )


async def _async_value(value: object) -> object:
    return value


VALID_TOKEN = "e30.eyJzdWIiOiJ1c2VyfDEyMyJ9.c2ln"


@dataclass
class FakeEntry:
    data: dict[str, Any]
    options: dict[str, Any]


class FakeHass:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def async_add_executor_job(self, function: object, *args: object) -> object:
        return function(*args)  # type: ignore[operator]


def test_fetch_usage_uses_cursor_cookie_headers_without_authorization(
    jwt_factory: object,
) -> None:
    """derive_session_cookie is exercised with a real JWT, not a monkeypatch."""
    token = jwt_factory()  # sub="google-oauth2|user-1"
    session = FakeSession(gets=[FakeResponse(200, json_data={"ok": True})])

    assert asyncio.run(_async_fetch_usage(session, token)) == {"ok": True}
    url, kwargs = session.get_calls[0]
    assert url == USAGE_API_URL
    cookie: str = kwargs["headers"]["Cookie"]
    # user_id is the portion after "|" in the sub claim ("user-1"); "::" is
    # URL-encoded to "%3A%3A" by derive_session_cookie.
    assert cookie.startswith("WorkosCursorSessionToken=user-1%3A%3A")
    assert kwargs["headers"] == {
        "Accept": "application/json",
        "Cookie": cookie,
        "Origin": "https://cursor.com",
        "Referer": "https://cursor.com/dashboard?tab=usage",
        "User-Agent": "hass-cursor-usage/1.0.0",
    }
    assert "Authorization" not in kwargs["headers"]
    assert kwargs["timeout"].total == 15


@pytest.mark.parametrize("status", [401, 403])
async def test_fetch_usage_classifies_unauthorized(status: int) -> None:
    with pytest.raises(UsageUnauthorized):
        await _async_fetch_usage(FakeSession(gets=[FakeResponse(status)]), VALID_TOKEN)


@pytest.mark.parametrize("status", [429, 500])
async def test_fetch_usage_classifies_transient_http_failure(status: int) -> None:
    token = "literal-secret-token"
    with pytest.raises(UpdateFailed) as raised:
        await _async_fetch_usage(FakeSession(gets=[FakeResponse(status, text=token)]), VALID_TOKEN)
    assert str(status) in str(raised.value)
    assert token not in str(raised.value)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (FakeResponse(200, json_data=[]), "JSON object"),
        (FakeResponse(200, json_error=ValueError("secret response")), "decoding"),
    ],
)
async def test_fetch_usage_rejects_invalid_json(response: FakeResponse, expected: str) -> None:
    with pytest.raises(UpdateFailed) as raised:
        await _async_fetch_usage(FakeSession(gets=[response]), VALID_TOKEN)
    assert expected.lower() in str(raised.value).lower()
    assert "secret response" not in str(raised.value)


async def test_invalid_token_subject_is_unauthorized_without_leaking_token() -> None:
    token = "literal-secret-token"
    with pytest.raises(UsageUnauthorized) as raised:
        await _async_fetch_usage(FakeSession(), token)
    assert token not in str(raised.value)


async def test_refresh_uses_cursor_contract() -> None:
    session = FakeSession(posts=[FakeResponse(200, json_data={"access_token": "new"})])

    assert await _async_request_token_refresh(session, "refresh-secret") == {"access_token": "new"}
    url, kwargs = session.post_calls[0]
    assert url == TOKEN_REFRESH_URL
    assert kwargs["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "hass-cursor-usage/1.0.0",
    }
    assert kwargs["json"]["refresh_token"] == "refresh-secret"
    assert kwargs["timeout"].total == 15


async def test_refresh_requires_access_token() -> None:
    with pytest.raises(UpdateFailed, match="access token"):
        await _async_request_token_refresh(
            FakeSession(posts=[FakeResponse(200, json_data={"refresh_token": "new"})]), "refresh"
        )


@pytest.mark.parametrize("status", [400, 401])
async def test_refresh_permanent_rejection(status: int) -> None:
    session = FakeSession(
        posts=[FakeResponse(status, text='{"error":"invalid_grant","detail":"refresh-secret"}')]
    )
    with pytest.raises(RefreshTokenRejectedError) as raised:
        await _async_request_token_refresh(session, "refresh-secret")
    assert "refresh-secret" not in str(raised.value)


@pytest.mark.parametrize("status", [429, 500])
async def test_refresh_transient_failure_has_only_safe_status(status: int) -> None:
    session = FakeSession(posts=[FakeResponse(status, text="refresh-secret")])
    with pytest.raises(UpdateFailed) as raised:
        await _async_request_token_refresh(session, "refresh-secret")
    assert str(status) in str(raised.value)
    assert "refresh-secret" not in str(raised.value)


def _coordinator(session: FakeSession) -> CursorUsageCoordinator:
    return CursorUsageCoordinator(
        FakeHass(session), FakeEntry(data={CONF_AUTH_FILE: "/auth.json"}, options={})
    )


async def test_coordinator_rereads_refreshes_once_and_retries_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(FakeSession())
    reads = 0
    refreshes = 0
    fetches = 0

    async def read(_path: str) -> CursorAuthFile:
        nonlocal reads
        reads += 1
        return _auth()

    async def refresh(*_args: object) -> str:
        nonlocal refreshes
        refreshes += 1
        return "new-access"

    async def fetch(_session: object, token: str) -> dict[str, object]:
        nonlocal fetches
        fetches += 1
        if fetches == 1:
            raise UsageUnauthorized
        assert token == "new-access"
        return {"raw": True}

    monkeypatch.setattr(coordinator, "_async_read_auth_file", read)
    monkeypatch.setattr(coordinator, "_async_refresh_access_token", refresh)
    monkeypatch.setattr(coordinator_module, "access_token_needs_refresh", lambda _token: False)
    monkeypatch.setattr(coordinator_module, "_async_fetch_usage", fetch)
    monkeypatch.setattr(coordinator_module.usage, "parse_usage", lambda raw: {"parsed": raw})

    assert await coordinator._async_update_data() == {"parsed": {"raw": True}}
    assert (reads, refreshes, fetches) == (2, 1, 2)


async def test_coordinator_does_not_refresh_twice_after_prerefresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(FakeSession())
    refreshes = 0

    async def refresh(*_args: object) -> str:
        nonlocal refreshes
        refreshes += 1
        return "new-access"

    async def unauthorized(*_args: object) -> dict[str, object]:
        raise UsageUnauthorized

    monkeypatch.setattr(coordinator, "_async_read_auth_file", lambda _path: _async_value(_auth()))
    monkeypatch.setattr(coordinator, "_async_refresh_access_token", refresh)
    monkeypatch.setattr(coordinator_module, "access_token_needs_refresh", lambda _token: True)
    monkeypatch.setattr(coordinator_module, "_async_fetch_usage", unauthorized)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
    assert refreshes == 1


async def test_coordinator_retry_unauthorized_fails_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = _coordinator(FakeSession())

    async def unauthorized(*_args: object) -> dict[str, object]:
        raise UsageUnauthorized

    monkeypatch.setattr(coordinator, "_async_read_auth_file", lambda _path: _async_value(_auth()))
    monkeypatch.setattr(
        coordinator,
        "_async_refresh_access_token",
        lambda *_args: _async_value("new"),
    )
    monkeypatch.setattr(coordinator_module, "access_token_needs_refresh", lambda _token: False)
    monkeypatch.setattr(coordinator_module, "_async_fetch_usage", unauthorized)

    with pytest.raises(ConfigEntryAuthFailed, match="Cursor"):
        await coordinator._async_update_data()


async def test_refresh_persistence_auth_file_error_becomes_update_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AuthFileError raised by persist_refreshed_tokens must not escape as-is.

    The coordinator must catch AuthFileError from the persistence step and
    re-raise it as UpdateFailed (a safe transient failure) so that sensitive
    path or filesystem details are not surfaced to HA as a credential error.
    """
    from custom_components.hass_cursor_usage.auth import AuthFileError as AuthErr

    coordinator = _coordinator(FakeSession())

    async def fake_request_refresh(_session: object, _token: str) -> dict:
        return {"access_token": "new-token"}

    def raise_auth_file_error(*_args: object, **_kwargs: object) -> None:
        raise AuthErr("Unable to inspect the Cursor auth file")

    monkeypatch.setattr(coordinator_module, "_async_request_token_refresh", fake_request_refresh)
    monkeypatch.setattr(coordinator_module, "persist_refreshed_tokens", raise_auth_file_error)

    with pytest.raises(UpdateFailed):
        await coordinator._async_refresh_access_token(
            FakeSession(), "/auth.json", _auth(refresh="refresh-token")
        )
