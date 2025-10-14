from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import streamlit as st
from .general_calendar import get_general_calendar
from . import backend_utils


def _parse_iso_date(date_str: str) -> datetime.date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def ensure_calendar_entries(
    user: Dict[str, Any],
    start_date_iso: str,
    end_date_iso: str,
) -> Dict[str, Any]:
    """
    Mirror the post-payment calendar workflow:
    1. Populate period_predictions via star prediction API for missing days.
    2. Trigger the GPT background updater for standard content via calendar API.
       Basic calendar entries are filled for every day regardless of prediction state.
    """
    collection = st.session_state.collection
    line_id = user.get("line_id")

    if not line_id:
        return {
            "updated_days": 0,
            "gpt_triggered": False,
            "basic_profile_days": 0,
            "basic_holiday_days": 0,
            "errors": ["Missing line_id on user record."],
        }

    try:
        start_date = _parse_iso_date(start_date_iso)
        end_date = _parse_iso_date(end_date_iso)
    except ValueError as exc:
        return {
            "updated_days": 0,
            "gpt_triggered": False,
            "errors": [f"Invalid date range: {exc}"],
        }

    if start_date > end_date:
        return {
            "updated_days": 0,
            "gpt_triggered": False,
            "errors": ["start_date is after end_date."],
        }

    # Reload fresh predictions to avoid stale in-memory copies
    fresh_user = collection.find_one({"_id": user["_id"]}, {"period_predictions": 1}) or {}
    predictions = fresh_user.get("period_predictions") or {}
    birth_date = user.get("birth_date")
    can_predict = bool(birth_date)

    current = start_date
    updated_days = 0
    errors: List[str] = []

    month_cache: Dict[Tuple[int, int], Dict[str, Dict[str, Any]]] = {}
    basic_profile_updates: Dict[str, Dict[str, Any]] = {}
    basic_holiday_updates: Dict[str, Dict[str, Any]] = {}

    while current <= end_date:
        date_key = current.strftime("%Y-%m-%d")
        if can_predict and date_key not in predictions:
            try:
                predictions[date_key] = _fetch_star_prediction(birth_date, date_key)
                updated_days += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{date_key}: {exc}")

        month_key = (current.year, current.month)
        if month_key not in month_cache:
            try:
                month_cache[month_key] = get_general_calendar(current.year, current.month)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"general calendar {month_key}: {exc}")
                month_cache[month_key] = {"profile": {}, "holiday": {}}

        month_data = month_cache[month_key]
        profile_entry = month_data.get("profile", {}).get(date_key)
        holiday_entry = month_data.get("holiday", {}).get(date_key)
        if profile_entry:
            basic_profile_updates[date_key] = profile_entry
        if holiday_entry:
            basic_holiday_updates[date_key] = holiday_entry

        current += timedelta(days=1)

    if updated_days:
        collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"period_predictions": predictions}},
        )

    basic_updates_payload: Dict[str, Any] = {}
    if basic_profile_updates:
        basic_updates_payload.update(
            {f"calendar_basic.profile.{k}": v for k, v in basic_profile_updates.items()}
        )
    if basic_holiday_updates:
        basic_updates_payload.update(
            {f"calendar_basic.holiday.{k}": v for k, v in basic_holiday_updates.items()}
        )
    if basic_updates_payload:
        collection.update_one({"_id": user["_id"]}, {"$set": basic_updates_payload})

    gpt_triggered = False
    if can_predict:
        try:
            backend_utils.run_UpdatePeriodGPTAll_in_background(line_id)
            gpt_triggered = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GPT background task: {exc}")

    result: Dict[str, Any] = {
        "updated_days": updated_days,
        "gpt_triggered": gpt_triggered,
        "basic_profile_days": len(basic_profile_updates),
        "basic_holiday_days": len(basic_holiday_updates),
    }
    if errors:
        result["errors"] = errors
    return result



def trigger_gpt_update(line_id: str) -> dict:
    try:
        backend_utils.run_UpdatePeriodGPTAll_in_background(line_id)
        return {"status": "started"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}

def _fetch_star_prediction(birth_date: str, target_date: str) -> Dict[str, Any]:
    return backend_utils.Api5StarPredict(birth_date, target_date)

