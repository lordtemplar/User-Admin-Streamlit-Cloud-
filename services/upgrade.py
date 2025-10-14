from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any

import pytz
from dateutil.relativedelta import relativedelta
import streamlit as st
from dateutil.relativedelta import relativedelta

from .packages import get_package

THAI_TZ = pytz.timezone("Asia/Bangkok")


def _add_duration(base_date: datetime.date, months: int, days: int):
    result = base_date
    if months:
        result = result + relativedelta(months=months)
    if days:
        result = result + timedelta(days=days)
    return result


def apply_package_upgrade(
    user: Dict[str, Any],
    package_key: str,
    *,
    reference_id: str,
    timestamp_iso: str,
    sub_type: str,
    payment_type: str,
) -> Dict[str, Any]:
    package = get_package(package_key)

    collection = st.session_state.collection
    now = datetime.now(THAI_TZ)
    today = now.date()

    existing_period = user.get("period_available") or {}
    last_end = existing_period.get("end_date")
    last_start = existing_period.get("start_date")

    months = int(package.get("duration", 0) or 0)
    days = int(package.get("duration_days", 0) or 0)

    last_end_dt = None

    if last_end:
        try:
            last_end_dt = datetime.strptime(last_end, "%Y-%m-%d").date()
            if last_end_dt < today:
                start_dt = today
                end_dt = _add_duration(today, months, days)
            else:
                preserved_start = (
                    datetime.strptime(last_start, "%Y-%m-%d").date()
                    if last_start
                    else today
                )
                start_dt = preserved_start
                end_dt = _add_duration(last_end_dt, months, days)
        except Exception:
            start_dt = today
            end_dt = _add_duration(today, months, days)
    else:
        start_dt = today
        end_dt = _add_duration(today, months, days)

    start_dt = min(start_dt, end_dt)

    user_question_left = int(user.get("user_question_left") or 0)
    extra_tokens = int(package.get("tokens", 0) or 0)
    new_token_balance = user_question_left + extra_tokens

    collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "period_available": {
                    "start_date": start_dt.strftime("%Y-%m-%d"),
                    "end_date": end_dt.strftime("%Y-%m-%d"),
                    "updated_at": now,
                },
                "user_question_left": new_token_balance,
            },
            "$push": {
                "history_log": {
                    "event": "buy_package",
                    "start_date": start_dt.strftime("%Y-%m-%d"),
                    "end_date": end_dt.strftime("%Y-%m-%d"),
                    "num_months": months,
                    "duration_days": days,
                    "packageId": package.get("id"),
                    "subType": sub_type,
                    "paymentType": payment_type,
                    "timestamp": timestamp_iso,
                    "referenceId": reference_id,
                }
            },
        },
    )

    if last_end_dt and last_end_dt >= today:
        calendar_start_dt = min(last_end_dt + timedelta(days=1), end_dt)
    else:
        calendar_start_dt = start_dt

    return {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "extra_tokens": extra_tokens,
        "new_token_balance": new_token_balance,
        "calendar_start_date": calendar_start_dt.strftime("%Y-%m-%d"),
        "package_id": package.get("id"),
        "reference_id": reference_id,
    }
