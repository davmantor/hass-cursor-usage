"""Cursor Usage integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import usage
from .auth import (
    AuthFileError,
    CursorAuthFile,
    RefreshTokenRejectedError,
    RefreshTokenResponseError,
    access_token_needs_refresh,
    build_refresh_request,
    derive_session_cookie,
    persist_refreshed_tokens,
    read_auth_file,
    refresh_rejection_from_response,
)
from .const import (
    CONF_AUTH_FILE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    TOKEN_REFRESH_URL,
    USAGE_API_URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type CursorUsageConfigEntry = ConfigEntry[CursorUsageCoordinator]


class UsageUnauthorized(Exception):
    """Raised when Cursor rejects the session used by the usage endpoint."""


async def async_setup_entry(hass: HomeAssistant, entry: CursorUsageConfigEntry) -> bool:
    """Set up Cursor Usage from a config entry."""
    coordinator = CursorUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CursorUsageConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: CursorUsageConfigEntry) -> None:
    """Apply an updated polling interval."""
    coordinator: CursorUsageCoordinator = entry.runtime_data
    interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)


class CursorUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Read Cursor credentials and fetch normalized usage data."""

    config_entry: CursorUsageConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CursorUsageConfigEntry) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and parse the latest Cursor usage summary."""
        auth_file = self.config_entry.data[CONF_AUTH_FILE]
        auth = await self._async_read_auth_file(auth_file)
        session = aiohttp_client.async_get_clientsession(self.hass)
        refreshed = False

        access_token = auth.access_token
        if access_token_needs_refresh(access_token):
            access_token = await self._async_refresh_access_token(session, auth_file, auth)
            refreshed = True

        try:
            raw = await _async_fetch_usage(session, access_token)
        except UsageUnauthorized as err:
            if refreshed:
                raise _auth_failed("Cursor authentication failed after token refresh") from err

            # The file may have changed since the first read. Always re-read before
            # refreshing, and perform exactly one refresh/retry cycle.
            auth = await self._async_read_auth_file(auth_file)
            access_token = await self._async_refresh_access_token(session, auth_file, auth)
            try:
                raw = await _async_fetch_usage(session, access_token)
            except UsageUnauthorized as retry_err:
                raise _auth_failed("Cursor authentication failed after retry") from retry_err

        return usage.parse_usage(raw)

    async def _async_read_auth_file(self, auth_file: str) -> CursorAuthFile:
        """Read credentials on the executor for every update."""
        try:
            return await self.hass.async_add_executor_job(read_auth_file, auth_file)
        except AuthFileError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_refresh_access_token(
        self,
        session: aiohttp.ClientSession,
        auth_file: str,
        auth: CursorAuthFile,
    ) -> str:
        """Refresh and persist Cursor credentials."""
        if not auth.refresh_token:
            raise _auth_failed("Cursor auth file has no refresh token")

        try:
            refresh_response = await _async_request_token_refresh(session, auth.refresh_token)
        except RefreshTokenRejectedError as err:
            raise _auth_failed("Cursor permanently rejected the refresh token") from err

        try:
            return await self.hass.async_add_executor_job(
                persist_refreshed_tokens,
                auth_file,
                auth.data,
                refresh_response,
            )
        except RefreshTokenResponseError as err:
            raise UpdateFailed("Cursor token refresh returned unusable credentials") from err
        except AuthFileError as err:
            raise UpdateFailed("Unable to persist refreshed Cursor credentials") from err
        except OSError as err:
            raise UpdateFailed("Unable to persist refreshed Cursor credentials") from err


def _auth_failed(reason: str) -> ConfigEntryAuthFailed:
    """Build a safe, actionable reauthentication failure."""
    return ConfigEntryAuthFailed(
        f"{reason}. Re-export fresh Cursor credentials and update the auth file."
    )


async def _async_request_token_refresh(
    session: aiohttp.ClientSession, refresh_token: str
) -> dict[str, Any]:
    """Request a fresh Cursor OAuth access token."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "hass-cursor-usage/1.0.0",
    }

    try:
        async with session.post(
            TOKEN_REFRESH_URL,
            headers=headers,
            json=build_refresh_request(refresh_token),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            if not 200 <= response.status < 300:
                body = await response.text()
                rejection = refresh_rejection_from_response(response.status, body)
                if rejection is not None:
                    raise rejection
                raise UpdateFailed(f"Error refreshing Cursor token: HTTP {response.status}")
            raw = await response.json()
    except (RefreshTokenRejectedError, UpdateFailed):
        raise
    except aiohttp.ClientError as err:
        raise UpdateFailed("Error contacting the Cursor token endpoint") from err
    except (TypeError, ValueError) as err:
        raise UpdateFailed("Error decoding Cursor token refresh response") from err

    if not isinstance(raw, dict):
        raise UpdateFailed("Cursor token refresh response was not a JSON object")
    access_token = raw.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise UpdateFailed("Cursor token refresh response did not include an access token")
    return raw


async def _async_fetch_usage(
    session: aiohttp.ClientSession, access_token: str | None
) -> dict[str, Any]:
    """Fetch usage using Cursor's WorkOS session cookie."""
    if not isinstance(access_token, str) or not access_token:
        raise UsageUnauthorized
    try:
        cookie = derive_session_cookie(access_token)
    except AuthFileError as err:
        raise UsageUnauthorized from err

    headers = {
        "Accept": "application/json",
        "Cookie": cookie,
        "Origin": "https://cursor.com",
        "Referer": "https://cursor.com/dashboard?tab=usage",
        "User-Agent": "hass-cursor-usage/1.0.0",
    }
    try:
        async with session.get(
            USAGE_API_URL,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            if response.status in (401, 403):
                raise UsageUnauthorized
            if not 200 <= response.status < 300:
                raise UpdateFailed(f"Error fetching Cursor usage: HTTP {response.status}")
            raw = await response.json()
    except (UsageUnauthorized, UpdateFailed):
        raise
    except aiohttp.ClientError as err:
        raise UpdateFailed("Error contacting the Cursor usage endpoint") from err
    except (TypeError, ValueError) as err:
        raise UpdateFailed("Error decoding Cursor usage data") from err

    if not isinstance(raw, dict):
        raise UpdateFailed("Cursor usage response was not a JSON object")
    return raw
