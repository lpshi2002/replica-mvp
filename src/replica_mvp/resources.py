"""Resource observations shared by development attempts and final evaluation."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any


FAILURE_CATEGORIES = {
    "implementation_defect", "quality_gap", "data_missing", "access_missing",
    "environment_error", "budget_exhausted", "research_gap",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("resource timestamp must include a timezone")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid resource timestamp") from None
    if parsed.utcoffset() is None:
        raise ValueError("resource timestamp must include a timezone")
    return parsed


def nonnegative(value: Any) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def validate_resources(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"measurements", "human_interventions"}:
        raise ValueError("invalid resource observations")
    if not isinstance(value["measurements"], list) or not isinstance(value["human_interventions"], list):
        raise ValueError("resource observations must be lists")
    fields = {"metric", "phase", "value", "unit", "status", "basis", "recorded_at"}
    for observation in value["measurements"]:
        if not isinstance(observation, dict) or set(observation) != fields:
            raise ValueError("invalid resource measurement")
        if any(not isinstance(observation[f], str) or not observation[f].strip()
               for f in ("metric", "phase", "unit", "basis")):
            raise ValueError("measurement requires metric, phase, unit and basis")
        status = observation["status"]
        if status not in {"measured", "estimated", "unknown"}:
            raise ValueError("invalid resource measurement status")
        if (observation["value"] is not None if status == "unknown"
                else not nonnegative(observation["value"])):
            raise ValueError("unknown measurements must be null; known values must be finite and nonnegative")
        timestamp(observation["recorded_at"])
    for action in value["human_interventions"]:
        if (not isinstance(action, dict)
                or set(action) != {"task", "seconds", "basis"}
                or any(not isinstance(action[f], str) or not action[f].strip() for f in ("task", "basis"))
                or (action["seconds"] is not None and not nonnegative(action["seconds"]))):
            raise ValueError("invalid human intervention observation")
    return value


def measurement(metric: str, phase: str, value: float | None, unit: str, basis: str) -> dict[str, Any]:
    return {
        "metric": metric, "phase": phase, "value": value, "unit": unit,
        "status": "unknown" if value is None else "measured",
        "basis": basis, "recorded_at": utc_now(),
    }


def unknown_resources() -> dict[str, Any]:
    return {
        "measurements": [
            measurement(metric, phase, None, unit, "Not measured; subscription billing is not execution cost.")
            for metric, phase, unit in (
                ("active_time", "development", "seconds"),
                ("waiting_time", "development", "seconds"),
                ("preparation_time", "data_preparation", "seconds"),
                ("economic_cost", "development", "unknown_currency"),
                ("economic_cost", "execution", "unknown_currency"),
                ("tokens", "execution", "tokens"),
            )
        ],
        "human_interventions": [],
    }


def validate_budget(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"time_limit_seconds", "cost_limit", "stop_on_blocked"}:
        raise ValueError("invalid experiment budget")
    seconds, cost = value["time_limit_seconds"], value["cost_limit"]
    if seconds is not None and (not nonnegative(seconds) or seconds <= 0):
        raise ValueError("budget time limit must be positive or null")
    if cost is not None and (
        not isinstance(cost, dict) or set(cost) != {"amount", "currency"}
        or not nonnegative(cost.get("amount"))
        or not isinstance(cost.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", cost["currency"])
    ):
        raise ValueError("invalid cost budget")
    if type(value["stop_on_blocked"]) is not bool:
        raise ValueError("stop_on_blocked must be boolean")
    return value


def budget_stop(budget: dict[str, Any], started_at: str, resources: list[dict[str, Any]]) -> str | None:
    limit = budget["time_limit_seconds"]
    if limit is not None and (datetime.now(timezone.utc) - timestamp(started_at)).total_seconds() >= limit:
        return "budget_exhausted"
    cost = budget["cost_limit"]
    if cost is not None:
        observed = [m for r in resources for m in r["measurements"]
                    if m["metric"] == "economic_cost"]
        if not observed or any(m["status"] != "measured" or m["unit"] != cost["currency"] for m in observed):
            return "budget_unverifiable"
        if sum(m["value"] for m in observed) >= cost["amount"]:
            return "budget_exhausted"
    return None
