from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

USAGE_MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "hass_cursor_usage" / "usage.py"
)


def load_usage_module():
    spec = importlib.util.spec_from_file_location("hass_cursor_usage_usage", USAGE_MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


usage = load_usage_module()


def test_parse_uses_direct_percent_and_z_reset() -> None:
    result = usage.parse_usage(
        {
            "billingCycleEnd": "2026-07-15T12:00:00Z",
            "individualUsage": {"plan": {"totalPercentUsed": 42.5, "used": 500, "limit": 2000}},
        }
    )

    assert result["monthly_usage"] == 42.5
    assert result["monthly_reset_time"] == datetime(2026, 7, 15, 12, tzinfo=UTC)


def test_parse_computes_rounded_percent_when_direct_value_is_missing() -> None:
    result = usage.parse_usage({"individualUsage": {"plan": {"used": 1, "limit": 3}}})

    assert result["monthly_usage"] == 33.3


def test_parse_preserves_over_limit_usage() -> None:
    result = usage.parse_usage({"individualUsage": {"plan": {"used": 2500, "limit": 2000}}})

    assert result["monthly_usage"] == 125.0


def test_parse_uses_fallback_when_direct_percent_is_a_huge_integer() -> None:
    result = usage.parse_usage(
        {"individualUsage": {"plan": {"totalPercentUsed": 10**400, "used": 1, "limit": 4}}}
    )

    assert result["monthly_usage"] == 25.0


@pytest.mark.parametrize(
    ("used", "limit"),
    [(1e308, 1e-308), (1e308, 1.0)],
)
def test_parse_omits_nonfinite_computed_percent(used: float, limit: float) -> None:
    result = usage.parse_usage({"individualUsage": {"plan": {"used": used, "limit": limit}}})

    assert "monthly_usage" not in result


def test_parse_returns_valid_partial_response_without_fake_zeroes() -> None:
    result = usage.parse_usage(
        {
            "billingCycleEnd": "2026-07-15T12:00:00Z",
            "individualUsage": {"plan": {"used": None, "limit": 2000}},
        }
    )

    assert result["monthly_reset_time"] == datetime(2026, 7, 15, 12, tzinfo=UTC)
    assert "monthly_usage" not in result
    assert "requests_used" not in result


@pytest.mark.parametrize(
    "individual_usage",
    [None, [], "plan", 1, {"plan": None}, {"plan": []}, {"plan": "usage"}],
)
def test_parse_reads_plan_only_from_nested_dictionaries(individual_usage: object) -> None:
    result = usage.parse_usage(
        {
            "individualUsage": individual_usage,
            "plan": {"totalPercentUsed": 25},
        }
    )

    assert result == {}


@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        None,
        "25",
        "",
        -1,
        10**400,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_parse_rejects_invalid_direct_percent_and_uses_valid_fallback(
    invalid: object,
) -> None:
    result = usage.parse_usage(
        {"individualUsage": {"plan": {"totalPercentUsed": invalid, "used": 1, "limit": 4}}}
    )

    assert result["monthly_usage"] == 25.0


@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        None,
        "25",
        "",
        -1,
        10**400,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_parse_omits_usage_for_invalid_used_values(invalid: object) -> None:
    result = usage.parse_usage({"individualUsage": {"plan": {"used": invalid, "limit": 100}}})

    assert "monthly_usage" not in result
    assert "requests_used" not in result


@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        None,
        "100",
        "",
        -1,
        0,
        10**400,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_parse_omits_usage_for_invalid_or_nonpositive_limits(invalid: object) -> None:
    result = usage.parse_usage({"individualUsage": {"plan": {"used": 25, "limit": invalid}}})

    assert "monthly_usage" not in result
    assert "requests_limit" not in result


@pytest.mark.parametrize(
    "invalid",
    [None, True, 123, "", "   ", "not-a-date", "2026-99-15T12:00:00Z"],
)
def test_parse_omits_invalid_timestamps(invalid: object) -> None:
    result = usage.parse_usage(
        {
            "billingCycleEnd": invalid,
            "individualUsage": {"plan": {"totalPercentUsed": 10}},
        }
    )

    assert result == {"monthly_usage": 10.0}


def test_parse_preserves_timestamp_offset() -> None:
    result = usage.parse_usage({"billingCycleEnd": "2026-07-15T12:00:00-07:00"})

    reset = result["monthly_reset_time"]
    assert reset == datetime(2026, 7, 15, 12, tzinfo=timezone(timedelta(hours=-7)))
    assert reset.utcoffset() == timedelta(hours=-7)


def test_parse_attaches_utc_to_naive_timestamp() -> None:
    result = usage.parse_usage({"billingCycleEnd": "2026-07-15T12:00:00"})

    assert result == {"monthly_reset_time": datetime(2026, 7, 15, 12, tzinfo=UTC)}


# ---------------------------------------------------------------------------
# New field tests
# ---------------------------------------------------------------------------

FULL_FIXTURE: dict = {
    "billingCycleStart": "2026-06-01T00:00:00Z",
    "billingCycleEnd": "2026-07-01T00:00:00Z",
    "membershipType": "pro",
    "isUnlimited": False,
    "individualUsage": {
        "plan": {
            "totalPercentUsed": 1.62,
            "used": 73,
            "limit": 2000,
            "remaining": 1927,
            "autoPercentUsed": 1.62,
            "apiPercentUsed": 0,
            "breakdown": {"included": 500, "bonus": 100},
        },
        "onDemand": {"enabled": True},
    },
}


def test_new_fields_all_present_in_full_fixture() -> None:
    result = usage.parse_usage(FULL_FIXTURE)

    assert result["requests_used"] == 73
    assert result["requests_limit"] == 2000
    assert result["requests_remaining"] == 1927
    assert result["auto_percent_used"] == 1.6
    assert result["api_percent_used"] == 0.0
    assert result["requests_included"] == 500
    assert result["requests_bonus"] == 100
    assert result["billing_cycle_start"] == datetime(2026, 6, 1, tzinfo=UTC)
    assert result["membership_type"] == "pro"
    assert result["is_unlimited"] == "false"
    assert result["on_demand_enabled"] == "true"


def test_is_unlimited_true_produces_string_true() -> None:
    raw = {**FULL_FIXTURE, "isUnlimited": True}
    assert usage.parse_usage(raw)["is_unlimited"] == "true"


def test_is_unlimited_false_produces_string_false() -> None:
    raw = {**FULL_FIXTURE, "isUnlimited": False}
    assert usage.parse_usage(raw)["is_unlimited"] == "false"


def test_on_demand_enabled_false_produces_string_false() -> None:
    raw = {**FULL_FIXTURE, "individualUsage": {**FULL_FIXTURE["individualUsage"], "onDemand": {"enabled": False}}}
    assert usage.parse_usage(raw)["on_demand_enabled"] == "false"


def test_integer_fields_accept_float_truncated_to_int() -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "used": 73.9, "remaining": 1926.1}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    result = usage.parse_usage(raw)
    assert result["requests_used"] == 73
    assert result["requests_remaining"] == 1926


@pytest.mark.parametrize("bad", [True, False, None, "73", ""])
def test_requests_used_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "used": bad}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "requests_used" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [True, False, None, "2000", ""])
def test_requests_limit_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "limit": bad}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "requests_limit" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [True, False, None, "1927", ""])
def test_requests_remaining_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "remaining": bad}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "requests_remaining" not in usage.parse_usage(raw)


def test_missing_breakdown_omits_included_and_bonus() -> None:
    plan = {k: v for k, v in FULL_FIXTURE["individualUsage"]["plan"].items() if k != "breakdown"}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    result = usage.parse_usage(raw)
    assert "requests_included" not in result
    assert "requests_bonus" not in result


@pytest.mark.parametrize("bad", [True, False, None, "500", ""])
def test_requests_included_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "breakdown": {"included": bad, "bonus": 100}}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "requests_included" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [True, False, None, "100", ""])
def test_requests_bonus_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "breakdown": {"included": 500, "bonus": bad}}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "requests_bonus" not in usage.parse_usage(raw)


def test_missing_on_demand_key_omits_on_demand_enabled() -> None:
    ind_no_ondemand = {k: v for k, v in FULL_FIXTURE["individualUsage"].items() if k != "onDemand"}
    raw = {**FULL_FIXTURE, "individualUsage": ind_no_ondemand}
    assert "on_demand_enabled" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [None, 1, "true", "false", 0])
def test_non_bool_is_unlimited_omits_field(bad: object) -> None:
    raw = {**FULL_FIXTURE, "isUnlimited": bad}
    assert "is_unlimited" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [None, 1, 42, [], {}])
def test_non_string_membership_type_omits_field(bad: object) -> None:
    raw = {**FULL_FIXTURE, "membershipType": bad}
    assert "membership_type" not in usage.parse_usage(raw)


def test_empty_string_membership_type_omits_field() -> None:
    raw = {**FULL_FIXTURE, "membershipType": ""}
    assert "membership_type" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [None, True, 123, "", "   ", "not-a-date"])
def test_billing_cycle_start_invalid_omits_field(bad: object) -> None:
    raw = {**FULL_FIXTURE, "billingCycleStart": bad}
    assert "billing_cycle_start" not in usage.parse_usage(raw)


@pytest.mark.parametrize("bad", [True, False, None, "1.62", ""])
def test_auto_percent_used_omitted_for_invalid_types(bad: object) -> None:
    plan = {**FULL_FIXTURE["individualUsage"]["plan"], "autoPercentUsed": bad}
    raw = {**FULL_FIXTURE, "individualUsage": {"plan": plan}}
    assert "auto_percent_used" not in usage.parse_usage(raw)
