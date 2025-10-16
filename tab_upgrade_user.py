"""Package upgrade tab."""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from services.calendar import ensure_calendar_entries
from services.packages import list_packages
from services.transactions import record_transaction
from services.upgrade import apply_package_upgrade
from um_utils import gen_reference_id, get_user_type, now_iso_ms_z, refresh_current_user


def _format_package_label(pkg: Dict) -> str:
    price = pkg.get("price")
    title = pkg.get("title", "N/A")
    description = pkg.get("description", "")
    if price in (None, 0):
        return f"{title} - {description}".strip(" -")
    return f"{title} (THB {price})"


def render_upgrade_user_tab(user):
    st.subheader("Upgrade package and token allowance")

    current_user_type = get_user_type(user)
    if current_user_type == "mu insight":
        period_info = user.get("period_available") or {}
        start_date = period_info.get("start_date")
        end_date = period_info.get("end_date")
        if start_date and end_date:
            st.success(f"This user already has an active mu insight package ({start_date} to {end_date}).")
        else:
            st.success("This user already has an active mu insight package.")
    else:
        st.info("This user is currently on a basic package.")

    st.markdown("---")

    packages = list_packages()
    if not packages:
        st.error("Package configuration is empty. Update services/packages.py.")
        return

    with st.form("upgrade_form"):
        selected_idx = st.selectbox(
            "Choose a package",
            options=list(range(len(packages))),
            format_func=lambda idx: _format_package_label(packages[idx]),
        )
        submitted = st.form_submit_button("Apply upgrade", use_container_width=True, type="primary")

    if not submitted:
        return

    selected_package = packages[selected_idx]
    line_id = user.get("line_id")
    if not line_id:
        st.error("The user record is missing a LINE ID.")
        return

    timestamp_iso = now_iso_ms_z()
    reference_id = gen_reference_id()
    sub_type = "standard"
    payment_type = "free"

    with st.status("Processing...", expanded=True) as status_box:
        status_box.write("1. Upgrade to mu insight")
        # Step 1: upgrade package (also extends mu insight period)
        try:
            result = apply_package_upgrade(
                user,
                selected_package["id"],
                reference_id=reference_id,
                timestamp_iso=timestamp_iso,
                sub_type=sub_type,
                payment_type=payment_type,
            )
            status_box.write("    Upgrade to mu insight")
        except Exception as exc:  # noqa: BLE001
            status_box.update(label="Upgrade failed.", state="error")
            st.error(f"Unable to apply the upgrade: {exc}")
            return

        status_box.write("2. Add Token")
        token_delta = result.get("extra_tokens", 0)
        new_balance = result.get("new_token_balance")
        status_box.write(f"    Add Token (delta {token_delta}, new balance {new_balance})")

    updated_user = st.session_state.collection.find_one({"_id": user["_id"]}) or user

    calendar_result: Dict[str, Any] = {}
    status_box.write("3. Add Basic Calendar")
    basic_ok = False
    try:
        calendar_result = ensure_calendar_entries(
            updated_user,
            result.get("calendar_start_date", result["start_date"]),
            result["end_date"],
        )
        star_days = calendar_result.get("updated_days", 0) or 0
        basic_days = calendar_result.get("basic_profile_days", 0) or 0
        holiday_days = calendar_result.get("basic_holiday_days", 0) or 0
        status_box.write(
            f"    Add Basic Calendar (star {star_days}, profile {basic_days}, holiday {holiday_days})"
        )
        basic_ok = True
    except Exception as exc:  # noqa: BLE001
        status_box.write(f"    Add Basic Calendar failed: {exc}")
        calendar_result = {}


    status_box.write("4. Add GPT Calendar")
    gpt_details_raw = calendar_result.get("gpt_details") if isinstance(calendar_result, dict) else None

    status_sources = []
    if isinstance(gpt_details_raw, dict):
        snapshot = gpt_details_raw.get("status_snapshot")
        if isinstance(snapshot, dict):
            status_sources.append(snapshot)
        status_sources.append(gpt_details_raw)
        response_info = gpt_details_raw.get("status_response")
        if isinstance(response_info, dict):
            status_sources.append(response_info)
        remote_info = gpt_details_raw.get("remote_details")
        if isinstance(remote_info, dict):
            status_sources.append(remote_info)
    else:
        snapshot = None
        response_info = None

    def _first_from_sources(key: str):
        for src in status_sources:
            if not isinstance(src, dict):
                continue
            value = src.get(key)
            if value not in (None, "", []):
                return value
        return None

    success_statuses = {"queued", "running", "started", "completed", "success", "ok", "processed"}
    gpt_status = _first_from_sources("status")
    gpt_triggered = bool(basic_ok and gpt_status in success_statuses)
    if gpt_triggered:
        status_box.write("    Add GPT Calendar request submitted.")
    elif gpt_status == "error":
        error_message = _first_from_sources("message") or "unknown error"
        status_box.write(f"    Add GPT Calendar failed: {error_message}")
    elif gpt_status == "skipped":
        skip_message = _first_from_sources("message") or "GPT calendar skipped."
        status_box.write(f"    Add GPT Calendar skipped: {skip_message}")
    else:
        status_box.write("    Add GPT Calendar did not start. Check configuration or logs.")

    if isinstance(gpt_details_raw, dict):
        info_parts = []
        message_text = _first_from_sources("message")
        if message_text and gpt_status not in {"error", "skipped"}:
            info_parts.append(message_text)
        processed = _first_from_sources("processed_dates")
        total = _first_from_sources("total_dates")
        if processed is not None and total is not None:
            info_parts.append(f"processed {processed}/{total}")
        failed_count = _first_from_sources("failed_count")
        if failed_count:
            info_parts.append(f"failed {failed_count}")
        queue_size = _first_from_sources("queue_size")
        if queue_size is not None:
            info_parts.append(f"queue size {queue_size}")
        line_ref = _first_from_sources("line_id")
        if line_ref:
            info_parts.append(f"line_id {line_ref}")
        if info_parts:
            status_box.write("    Details: " + " | ".join(str(part) for part in info_parts))

        last_request = _first_from_sources("last_request")
        if isinstance(last_request, dict):
            request_date = last_request.get("date", "unknown date")
            request_status = last_request.get("status", "unknown")
            request_message = last_request.get("message", "")
            status_box.write(
                f"    Last request: {request_date} ({request_status}) {request_message}".strip()
            )

        failures = None
        for src in status_sources:
            if not isinstance(src, dict):
                continue
            failure_list = src.get("failed_results")
            if isinstance(failure_list, list) and failure_list:
                failures = failure_list
                break
        if failures:
            status_box.write("    Recent GPT failures:")
            for failure in failures:
                failure_date = failure.get("date", "unknown date")
                failure_msg = failure.get("error", "unknown error")
                status_box.write(f"      - {failure_date}: {failure_msg}")
    errors = calendar_result.get("errors") if isinstance(calendar_result, dict) else None
    if errors:
        status_box.write("    Calendar update completed with warnings:")
        for err in errors if isinstance(errors, list) else [errors]:
            status_box.write(f"     - {err}")

    failed_count_value = 0
    if '_first_from_sources' in locals():
        failed_raw = _first_from_sources("failed_count")
        try:
            failed_count_value = int(failed_raw or 0)
        except (TypeError, ValueError):
            failed_count_value = 0

    final_state = "complete"
    if not basic_ok or gpt_status == "error" or failed_count_value > 0:
        final_state = "error"

    status_box.update(label="Processing complete." if final_state == "complete" else "Processing finished with errors.", state=final_state)
    if final_state == "complete":
        st.toast("Package upgrade workflow completed")
    else:
        st.warning("Upgrade workflow finished with errors. Review the steps above.")

    try:
        record_transaction(
            user=updated_user,
            package=selected_package,
            reference_id=reference_id,
            timestamp_iso=timestamp_iso,
            sub_type=sub_type,
            payment_type=payment_type,
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Failed to record transaction: {exc}")

    refresh_current_user()

    summary = dict(result)
    summary["package"] = selected_package.get("title")
    summary["reference_id"] = reference_id
    summary["calendar_result"] = calendar_result
    st.json(summary, expanded=False)
