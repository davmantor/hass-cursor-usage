"""Tests for the CursorUsageSensor class.

Pure tests — no HA test framework required.  HA modules are stubbed so the
sensor module can be imported without a running HA instance.

Run with:
    PYTHONPATH=. pytest -q tests/test_sensor.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Stub homeassistant before importing the package (mirrors test_config_flow.py)
# ---------------------------------------------------------------------------

try:
    import homeassistant  # noqa: F401
except ImportError:
    _ha = types.ModuleType("homeassistant")
    _ha.__path__ = []
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

    class _Platform:
        SENSOR = "sensor"

    _const.Platform = _Platform

    _core.HomeAssistant = object
    _core.callback = lambda f: f

    class _ConfigEntryAuthFailed(Exception):
        pass

    _exceptions.ConfigEntryAuthFailed = _ConfigEntryAuthFailed

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

    _aiohttp_client.async_get_clientsession = lambda hass: None

    class _DeviceEntryType:
        SERVICE = "service"

    class _DeviceInfo(dict):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)

    _device_registry.DeviceEntryType = _DeviceEntryType
    _device_registry.DeviceInfo = _DeviceInfo

    _entity_platform.AddEntitiesCallback = object

    class _SensorEntity:
        pass

    class _SensorDeviceClass:
        TIMESTAMP = "timestamp"

    class _SensorStateClass:
        MEASUREMENT = "measurement"

    _sensor_comp.SensorEntity = _SensorEntity
    _sensor_comp.SensorDeviceClass = _SensorDeviceClass
    _sensor_comp.SensorStateClass = _SensorStateClass

    class _CoordinatorEntity:
        def __init_subclass__(cls, **kw: object) -> None:
            super().__init_subclass__(**kw)

        def __class_getitem__(cls, _item: object) -> type:
            return cls

        def __init__(self, coordinator: object) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return self.coordinator.last_update_success

    _update_coord.CoordinatorEntity = _CoordinatorEntity

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

# ---------------------------------------------------------------------------
# Load the sensor module via importlib (avoids running async_setup_entry)
# ---------------------------------------------------------------------------

_SENSOR_PATH = (
    Path(__file__).parents[1] / "custom_components" / "hass_cursor_usage" / "sensor.py"
)


def _load_sensor_module() -> types.ModuleType:
    # Ensure the package __init__ stubs are present so relative imports work.
    pkg_dir = _SENSOR_PATH.parent
    pkg_name = "custom_components.hass_cursor_usage"

    if pkg_name not in sys.modules:
        # Stub the package init so `from . import ...` resolves.
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_dir)]
        pkg.__package__ = pkg_name
        # Provide the names imported by sensor.py from the package __init__.
        pkg.CursorUsageConfigEntry = object
        pkg.CursorUsageCoordinator = object
        sys.modules[pkg_name] = pkg

        parent = types.ModuleType("custom_components")
        parent.__path__ = [str(pkg_dir.parent)]
        sys.modules.setdefault("custom_components", parent)

    if "custom_components.hass_cursor_usage.const" not in sys.modules:
        const_spec = importlib.util.spec_from_file_location(
            "custom_components.hass_cursor_usage.const", pkg_dir / "const.py"
        )
        assert const_spec is not None
        const_mod = importlib.util.module_from_spec(const_spec)
        sys.modules["custom_components.hass_cursor_usage.const"] = const_mod
        assert const_spec.loader is not None
        const_spec.loader.exec_module(const_mod)

    spec = importlib.util.spec_from_file_location(
        "custom_components.hass_cursor_usage.sensor", _SENSOR_PATH
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sensor_mod = _load_sensor_module()
CursorUsageSensor = sensor_mod.CursorUsageSensor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockCoordinator:
    """Minimal coordinator stand-in."""

    def __init__(self, *, last_update_success: bool = True, data: object = None) -> None:
        self.last_update_success = last_update_success
        self.data = data


class _MockEntry:
    """Minimal config entry stand-in."""

    entry_id = "test_entry_id"


def _make_sensor(key: str, coordinator: _MockCoordinator) -> CursorUsageSensor:
    entry = _MockEntry()
    # Pull definition metadata from SENSOR_DEFINITIONS for the given key.
    from custom_components.hass_cursor_usage.const import SENSOR_DEFINITIONS

    for defn in SENSOR_DEFINITIONS:
        if defn[0] == key:
            _, name, unit, icon, device_class = defn
            break
    else:
        name, unit, icon, device_class = key, None, "mdi:alert", None

    return CursorUsageSensor(coordinator, entry, key, name, unit, icon, device_class)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_api_error_returns_1_on_update_failure() -> None:
    """api_error sensor must return 1 when the last coordinator update failed."""
    coordinator = _MockCoordinator(last_update_success=False, data=None)
    sensor = _make_sensor("api_error", coordinator)

    assert sensor.native_value == 1


def test_api_error_returns_0_on_update_success() -> None:
    """api_error sensor must return 0 when the last coordinator update succeeded."""
    coordinator = _MockCoordinator(last_update_success=True, data={})
    sensor = _make_sensor("api_error", coordinator)

    assert sensor.native_value == 0


def test_non_api_error_sensor_unavailable_when_key_missing() -> None:
    """A data sensor is unavailable when its key is absent from coordinator data."""
    coordinator = _MockCoordinator(last_update_success=True, data={})
    sensor = _make_sensor("monthly_usage", coordinator)

    assert sensor.available is False


def test_api_error_sensor_always_available() -> None:
    """api_error sensor is available even when data is None."""
    coordinator = _MockCoordinator(last_update_success=False, data=None)
    sensor = _make_sensor("api_error", coordinator)

    assert sensor.available is True
