"""Normalize Cursor Individual usage responses."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def parse_usage(raw: dict[str, Any]) -> dict[str, Any]:
    """Return valid usage metrics from a Cursor Individual response."""
    data: dict[str, Any] = {}
    individual = raw.get("individualUsage")
    plan = individual.get("plan") if isinstance(individual, dict) else None

    if isinstance(plan, dict):
        direct = _non_negative_number(plan.get("totalPercentUsed"))
        if direct is not None:
            data["monthly_usage"] = direct
        else:
            used = _non_negative_number(plan.get("used"))
            limit = _positive_number(plan.get("limit"))
            if used is not None and limit is not None:
                computed = used / limit * 100
                if math.isfinite(computed):
                    data["monthly_usage"] = round(computed, 2)

        req_used = _non_negative_integer(plan.get("used"))
        if req_used is not None:
            data["requests_used"] = req_used

        req_limit = _positive_integer(plan.get("limit"))
        if req_limit is not None:
            data["requests_limit"] = req_limit

        req_remaining = _non_negative_integer(plan.get("remaining"))
        if req_remaining is not None:
            data["requests_remaining"] = req_remaining

        auto_pct = _non_negative_number(plan.get("autoPercentUsed"))
        if auto_pct is not None:
            data["auto_percent_used"] = auto_pct

        api_pct = _non_negative_number(plan.get("apiPercentUsed"))
        if api_pct is not None:
            data["api_percent_used"] = api_pct

        breakdown = plan.get("breakdown")
        if isinstance(breakdown, dict):
            req_included = _non_negative_integer(breakdown.get("included"))
            if req_included is not None:
                data["requests_included"] = req_included

            req_bonus = _non_negative_integer(breakdown.get("bonus"))
            if req_bonus is not None:
                data["requests_bonus"] = req_bonus

    reset = _timestamp(raw.get("billingCycleEnd"))
    if reset is not None:
        data["monthly_reset_time"] = reset

    cycle_start = _timestamp(raw.get("billingCycleStart"))
    if cycle_start is not None:
        data["billing_cycle_start"] = cycle_start

    membership = raw.get("membershipType")
    if isinstance(membership, str) and membership:
        data["membership_type"] = membership

    is_unlimited = raw.get("isUnlimited")
    if isinstance(is_unlimited, bool):
        data["is_unlimited"] = "true" if is_unlimited else "false"

    on_demand = individual.get("onDemand") if isinstance(individual, dict) else None
    if isinstance(on_demand, dict):
        on_demand_enabled = on_demand.get("enabled")
        if isinstance(on_demand_enabled, bool):
            data["on_demand_enabled"] = "true" if on_demand_enabled else "false"

    return data


def _non_negative_integer(value: Any) -> int | None:
    """Return a non-negative integer, or None if invalid.

    Rejects booleans, non-numeric types, non-finite floats, and integers
    too large to be represented as a float (consistent with _non_negative_number).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        n = int(value)
        float(n)  # reject integers too large to represent as float (e.g. 10**400)
    except (ValueError, OverflowError):
        return None
    return n if n >= 0 else None


def _positive_integer(value: Any) -> int | None:
    """Return a positive integer, or None if invalid."""
    n = _non_negative_integer(value)
    return n if n is not None and n > 0 else None


def _non_negative_number(value: Any) -> float | None:
    """Return a finite nonnegative number as a float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _positive_number(value: Any) -> float | None:
    """Return a finite positive number as a float."""
    number = _non_negative_number(value)
    return number if number is not None and number > 0 else None


def _timestamp(value: Any) -> datetime | None:
    """Return a timezone-aware datetime for a valid ISO timestamp."""
    if not isinstance(value, str) or not value:
        return None

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
