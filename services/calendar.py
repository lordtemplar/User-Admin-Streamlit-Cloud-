from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import requests
import streamlit as st

import config
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
    gpt_details: Dict[str, Any] | None = None
    success_statuses = {"queued", "running", "started", "completed", "success", "ok", "processed"}

    if can_predict:
        remote_details = _trigger_remote_calendar_fix(line_id)
        status_response = None
        status_snapshot = None
        status_value = remote_details.get("status") if isinstance(remote_details, dict) else None

        if status_value in success_statuses:
            gpt_triggered = True

        if status_value and status_value not in success_statuses:
            message_text = remote_details.get("message") if isinstance(remote_details, dict) else None
            errors.append(f"Remote GPT trigger failed: {message_text or status_value}")

        if status_value not in success_statuses:
            try:
                status_response = backend_utils.run_UpdatePeriodGPTAll_in_background(line_id)
                status_snapshot = backend_utils.get_gpt_task_status(line_id)
                snapshot_status = status_snapshot.get("status") if isinstance(status_snapshot, dict) else None
                response_status = status_response.get("status") if isinstance(status_response, dict) else None
                status_value = snapshot_status or response_status or status_value
                if status_value in success_statuses:
                    gpt_triggered = True
            except Exception as exc:  # noqa: BLE001
                errors.append(f"GPT background task: {exc}")
                status_response = {"status": "error", "message": str(exc), "line_id": line_id}

        gpt_details = {
            "status": status_value,
            "remote_details": remote_details,
            "status_response": status_response,
            "status_snapshot": status_snapshot,
        }
    else:
        gpt_details = {"status": "skipped", "message": "User missing birth_date; GPT calendar skipped.", "line_id": line_id}

    result: Dict[str, Any] = {
        "updated_days": updated_days,
        "gpt_triggered": gpt_triggered,
        "basic_profile_days": len(basic_profile_updates),
        "basic_holiday_days": len(basic_holiday_updates),
    }
    if gpt_details is not None:
        result["gpt_details"] = gpt_details
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


def _trigger_remote_calendar_fix(line_id: str) -> Dict[str, Any]:
    base_url = (config.API_BASE_URL or "").rstrip("/")
    if not base_url:
        return {"status": "skipped", "message": "API_BASE_URL is not configured.", "line_id": line_id}

    url = f"{base_url}/calendar/fix"
    params = {"line_id": line_id}
    try:
        response = requests.post(url, params=params, timeout=(5, 60))
    except requests.Timeout as exc:
        return {"status": "timeout", "message": f"{exc}", "line_id": line_id}
    except requests.RequestException as exc:
        return {"status": "error", "message": f"{exc}", "line_id": line_id}

    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {"raw": response.text}

    if response.status_code >= 400:
        return {
            "status": "error",
            "message": payload if isinstance(payload, str) else payload or response.text,
            "http_status": response.status_code,
            "line_id": line_id,
        }

    remote_status = payload.get("status") if isinstance(payload, dict) else None
    if not remote_status:
        remote_status = "started"

    return {
        "status": remote_status,
        "message": payload.get("message") if isinstance(payload, dict) else None,
        "http_status": response.status_code,
        "payload": payload,
        "line_id": line_id,
    }

