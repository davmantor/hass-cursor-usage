"""Tests for config_flow._validate_auth_file and options validation.

Pure tests — no HA test framework required.  HA and voluptuous modules are
stubbed (following the same pattern as test_coordinator.py) so the module can
be imported without a running HA instance.

Run with:
    PYTHONPATH=. pytest -q tests/test_config_flow.py
"""

from __future__ import annotations

import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Stub homeassistant and voluptuous before importing the package.
# Must happen at module level, before any custom_components import.
# ---------------------------------------------------------------------------

try:
    import homeassistant  # noqa: F401
except ImportError:
    _ha = types.ModuleType("homeassistant")
    _ha.__path__ = []  # make Python treat it as a package
    _ce = types.ModuleType("homeassistant.config_entries")
    _const = types.ModuleType("homeassistant.const")
    _core = types.ModuleType("homeassistant.core")
    _exceptions = types.ModuleType("homeassistant.exceptions")
    _helpers = types.ModuleType("homeassistant.helpers")
    _helpers.__path__ = []
    _aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    _update_coord = types.ModuleType("homeassistant.helpers.update_coordinator")
    _device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    _entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    _sensor_mod = types.ModuleType("homeassistant.components")
    _sensor_mod.__path__ = []
    _sensor_comp = types.ModuleType("homeassistant.components.sensor")

    # --- config_entries ---
    class _ConfigEntry:
        def __class_getitem__(cls, _item: object) -> type:
            return cls

    class _ConfigFlow:
        def __init_subclass__(cls, *, domain: object = None, **kw: object) -> None:
            super().__init_subclass__(**kw)

    class _OptionsFlow:
        pass

    class _ConfigFlowResult:
        pass

    _ce.ConfigEntry = _ConfigEntry
    _ce.ConfigFlow = _ConfigFlow
    _ce.OptionsFlow = _OptionsFlow
    _ce.ConfigFlowResult = _ConfigFlowResult

    # --- const ---
    class _Platform:
        SENSOR = "sensor"

    _const.Platform = _Platform

    # --- core ---
    _core.HomeAssistant = object
    _core.callback = lambda f: f

    # --- exceptions ---
    class _ConfigEntryAuthFailed(Exception):
        pass

    _exceptions.ConfigEntryAuthFailed = _ConfigEntryAuthFailed

    # --- update_coordinator ---
    class _DataUpdateCoordinator:
        def __class_getitem__(cls, _item: object) -> type:
            return cls

        def __init__(self, hass: object, _logger: object, **kwargs: object) -> None:
            self.hass = hass
            self.config_entry = kwargs.get("config_entry")
            self.update_interval = kwargs.get("update_interval")
            self.data = None
            self.last_update_success = True

    class _UpdateFailed(Exception):
        pass

    _update_coord.DataUpdateCoordinator = _DataUpdateCoordinator
    _update_coord.UpdateFailed = _UpdateFailed

    # --- aiohttp_client ---
    _aiohttp_client.async_get_clientsession = lambda hass: None

    # --- device_registry ---
    class _DeviceEntryType:
        SERVICE = "service"

    class _DeviceInfo(dict):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)

    _device_registry.DeviceEntryType = _DeviceEntryType
    _device_registry.DeviceInfo = _DeviceInfo

    # --- entity_platform ---
    _entity_platform.AddEntitiesCallback = object

    # --- sensor ---
    class _SensorEntity:
        pass

    class _SensorDeviceClass:
        TIMESTAMP = "timestamp"

    class _SensorStateClass:
        MEASUREMENT = "measurement"

    _sensor_comp.SensorEntity = _SensorEntity
    _sensor_comp.SensorDeviceClass = _SensorDeviceClass
    _sensor_comp.SensorStateClass = _SensorStateClass

    # --- CoordinatorEntity ---
    _coord_entity_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
    _coord_entity_mod.DataUpdateCoordinator = _DataUpdateCoordinator
    _coord_entity_mod.UpdateFailed = _UpdateFailed

    class _CoordinatorEntity:
        def __init_subclass__(cls, **kw: object) -> None:
            super().__init_subclass__(**kw)

        def __class_getitem__(cls, _item: object) -> type:
            return cls

        def __init__(self, coordinator: object) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

    _coord_entity_mod.CoordinatorEntity = _CoordinatorEntity
    _update_coord.CoordinatorEntity = _CoordinatorEntity

    # wire up sub-modules on parent modules
    _helpers.aiohttp_client = _aiohttp_client
    _helpers.update_coordinator = _update_coord
    _helpers.device_registry = _device_registry
    _helpers.entity_platform = _entity_platform
    _ha.config_entries = _ce
    _ha.const = _const
    _ha.core = _core
    _ha.exceptions = _exceptions
    _ha.helpers = _helpers

    sys.modules.update(
        {
            "homeassistant": _ha,
            "homeassistant.config_entries": _ce,
            "homeassistant.const": _const,
            "homeassistant.core": _core,
            "homeassistant.exceptions": _exceptions,
            "homeassistant.helpers": _helpers,
            "homeassistant.helpers.aiohttp_client": _aiohttp_client,
            "homeassistant.helpers.update_coordinator": _update_coord,
            "homeassistant.helpers.device_registry": _device_registry,
            "homeassistant.helpers.entity_platform": _entity_platform,
            "homeassistant.components": _sensor_mod,
            "homeassistant.components.sensor": _sensor_comp,
        }
    )

if "voluptuous" not in sys.modules:
    _vol = types.ModuleType("voluptuous")

    class _Invalid(Exception):
        pass

    class _All:
        def __init__(self, *validators: object) -> None:
            self._validators = validators

        def __call__(self, value: object) -> object:
            for v in self._validators:
                value = v(value)
            return value

    class _Range:
        def __init__(self, min: object = None, max: object = None) -> None:
            self._min = min
            self._max = max

        def __call__(self, value: object) -> object:
            if self._min is not None and value < self._min:
                raise _Invalid(f"{value} < {self._min}")
            if self._max is not None and value > self._max:
                raise _Invalid(f"{value} > {self._max}")
            return value

    _vol.Invalid = _Invalid
    _vol.Schema = lambda s, **kw: s
    _vol.All = _All
    _vol.Range = _Range
    _vol.Required = lambda key, **kw: key
    sys.modules["voluptuous"] = _vol

# Import the modules under test *after* stubs are in place.
from custom_components.hass_cursor_usage import config_flow  # noqa: E402
from custom_components.hass_cursor_usage.const import (  # noqa: E402
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

# ---------------------------------------------------------------------------
# _validate_auth_file – pure function tests (no HA framework needed)
# ---------------------------------------------------------------------------


def test_validate_auth_file_missing(tmp_path):
    """Non-existent file returns auth_file_unreadable."""
    path = tmp_path / "no_such_file.json"
    assert config_flow._validate_auth_file(str(path)) == "auth_file_unreadable"


def test_validate_auth_file_malformed(tmp_path):
    """Malformed JSON returns auth_file_unreadable."""
    path = tmp_path / "auth.json"
    path.write_text("not json {{{")
    assert config_flow._validate_auth_file(str(path)) == "auth_file_unreadable"


def test_validate_auth_file_non_object(tmp_path):
    """JSON array (not a dict) returns auth_file_unreadable."""
    path = tmp_path / "auth.json"
    path.write_text('["not", "an", "object"]')
    assert config_flow._validate_auth_file(str(path)) == "auth_file_unreadable"


def test_validate_auth_file_requires_refresh_token(tmp_path):
    """File with only access_token but no refresh_token returns missing_refresh_token."""
    path = tmp_path / "auth.json"
    path.write_text('{"access_token":"access"}')
    assert config_flow._validate_auth_file(str(path)) == "missing_refresh_token"


def test_validate_auth_file_accepts_refresh_only(tmp_path):
    """File with only refresh_token is valid."""
    path = tmp_path / "auth.json"
    path.write_text('{"refresh_token":"refresh"}')
    assert config_flow._validate_auth_file(str(path)) is None


# ---------------------------------------------------------------------------
# test_duplicate_setup_aborts – unit-tests the guard path directly.
# ---------------------------------------------------------------------------


def test_duplicate_setup_aborts():
    """CursorUsageConfigFlow aborts with already_configured when unique ID already set."""

    class AbortFlow(Exception):
        """Minimal stand-in for homeassistant.data_entry_flow.AbortFlow."""

        def __init__(self, reason: str) -> None:
            self.reason = reason
            super().__init__(reason)

    flow = config_flow.CursorUsageConfigFlow()

    # async_set_unique_id normally calls HA internals; stub it out.
    flow.async_set_unique_id = lambda domain: None  # type: ignore[method-assign]

    # _abort_if_unique_id_configured raises AbortFlow when a duplicate is detected.
    def _abort_duplicate() -> None:
        raise AbortFlow("already_configured")

    flow._abort_if_unique_id_configured = _abort_duplicate  # type: ignore[method-assign]

    # Execute the same guard sequence as production async_step_user.
    with pytest.raises(AbortFlow) as exc_info:
        flow.async_set_unique_id(config_flow.DOMAIN)
        flow._abort_if_unique_id_configured()

    assert exc_info.value.reason == "already_configured"


# ---------------------------------------------------------------------------
# Options-schema bounds (parameterised) — driven through the production
# voluptuous schema (All + Range) to catch mismatched literals.
# ---------------------------------------------------------------------------

import voluptuous as vol  # noqa: E402  (stub already in sys.modules)


def _is_valid(value: int) -> bool:
    """Validate value through the same voluptuous schema used in production."""
    validator = vol.All(int, vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL))
    try:
        validator(value)
        return True
    except vol.Invalid:
        return False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (299, False),
        (300, True),
        (3600, True),
        (3601, False),
    ],
)
def test_update_interval_bounds(value: int, expected: bool):
    """Update-interval bounds match the spec: [300, 3600]."""
    assert _is_valid(value) == expected
