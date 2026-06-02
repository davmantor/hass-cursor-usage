"""Codex Usage integration for Home Assistant."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTH_FILE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    USAGE_API_URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type CodexUsageConfigEntry = ConfigEntry[CodexUsageCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Set up Codex Usage from a config entry."""
    coordinator = CodexUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
    """Handle options update."""
    coordinator: CodexUsageCoordinator = entry.runtime_data
    interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)


class CodexUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch Codex usage data."""

    config_entry: CodexUsageConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
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
        """Fetch usage data from the Codex usage API."""
        auth_file = self.config_entry.data[CONF_AUTH_FILE]
        access_token = await self.hass.async_add_executor_job(_read_access_token, auth_file)
        if access_token is None:
            raise ConfigEntryAuthFailed("Codex auth file is missing an access token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Originator": "codex_cli_rs",
            "User-Agent": "hass-codex-usage",
        }

        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            resp = await session.get(
                USAGE_API_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            )
            if resp.status == 401:
                raise ConfigEntryAuthFailed(
                    "Codex authentication failed. Refresh the auth file with Codex login."
                )
            resp.raise_for_status()
            raw = await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching usage data: {err}") from err

        return _parse_usage(raw)


def _read_access_token(auth_file: str) -> str | None:
    """Read the access token from the Codex auth file."""
    try:
        with Path(auth_file).expanduser().open(encoding="utf-8") as file:
            auth_data = json.load(file)
    except (OSError, json.JSONDecodeError):
        _LOGGER.exception("Unable to read Codex auth file")
        return None

    tokens = auth_data.get("tokens")
    if not isinstance(tokens, dict):
        return None

    access_token = tokens.get("access_token")
    return access_token if isinstance(access_token, str) and access_token else None


def _parse_usage(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse raw Codex usage responses into a flat sensor data dict."""
    data: dict[str, Any] = {}
    rate_limits = _get_rate_limits(raw)

    primary = _get_window(rate_limits, "primary", "primary_window")
    if primary:
        data["session_usage_percent"] = _get_percent(primary)
        data["session_reset_time"] = _get_reset_time(primary)

    secondary = _get_window(rate_limits, "secondary", "secondary_window")
    if secondary:
        utilization = _get_percent(secondary)
        reset_time = _get_reset_time(secondary)
        data["week_usage_percent"] = utilization
        data["week_reset_time"] = reset_time
        data["week_usage_pace"] = _calculate_pace(
            utilization, reset_time, _get_window_minutes(secondary)
        )

    # Handle Credits (OpenAI can return a float 0.0 or a dict)
    credits = rate_limits.get("credits")
    if isinstance(credits, dict):
        data["credits_balance"] = _number_or_none(credits.get("balance"))
        data["credits_enabled"] = credits.get("hasCredits")
    elif isinstance(credits, int | float):
        data["credits_balance"] = float(credits)
        data["credits_enabled"] = credits > 0
    else:
        data["credits_balance"] = 0.0
        data["credits_enabled"] = False

    reached = rate_limits.get("rateLimitReachedType") or rate_limits.get("rate_limit_reached_type")
    data["rate_limit_reached"] = reached or "none"

    return data


def _get_rate_limits(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the rate-limit object from known Codex response shapes."""
    rate_limits = raw.get("rateLimits") or raw.get("rate_limit")
    if isinstance(rate_limits, dict):
        return rate_limits

    codex_limits = raw.get("rateLimitsByLimitId", {}).get("codex")
    if isinstance(codex_limits, dict):
        return codex_limits

    return raw


def _get_window(rate_limits: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    """Return a usage window from any known key."""
    for key in keys:
        window = rate_limits.get(key)
        if isinstance(window, dict):
            return window
    return None


def _get_percent(window: dict[str, Any]) -> float | int | None:
    """Return a window utilization percentage."""
    if "usedPercent" in window:
        return _number_or_none(window["usedPercent"])
    return _number_or_none(window.get("used_percent"))


def _get_reset_time(window: dict[str, Any]) -> datetime | None:
    """Return a window reset timestamp."""
    reset_value = window.get("resetsAt") or window.get("resets_at")
    if reset_value is None:
        return None

    if isinstance(reset_value, int | float):
        return datetime.fromtimestamp(reset_value, UTC)

    if isinstance(reset_value, str):
        try:
            return datetime.fromisoformat(reset_value)
        except ValueError:
            return None

    return None


def _get_window_minutes(window: dict[str, Any]) -> int | float | None:
    """Return a window duration in minutes."""
    for key in ("windowDurationMins", "window_duration_mins", "window_minutes"):
        if key in window:
            return _number_or_none(window[key])
    return None


def _calculate_pace(
    utilization: float | int | None, reset_time: datetime | None, window_minutes: float | int | None
) -> float | None:
    """Calculate how far usage is ahead of or behind the quota window."""
    if utilization is None or reset_time is None or not window_minutes:
        return None

    now = datetime.now(UTC)
    if reset_time.tzinfo is None:
        reset_time = reset_time.replace(tzinfo=UTC)

    window_seconds = window_minutes * 60
    elapsed = window_seconds - (reset_time - now).total_seconds()
    percent_elapsed = (elapsed / window_seconds) * 100
    return round(utilization - percent_elapsed, 1)


def _number_or_none(value: Any) -> float | int | None:
    """Return a numeric value when possible."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
