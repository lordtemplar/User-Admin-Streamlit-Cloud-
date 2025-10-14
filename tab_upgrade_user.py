"""Package upgrade tab."""
from __future__ import annotations

from typing import Dict

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

    with st.status("Applying package upgrade...", expanded=False) as status_box:
        try:
            result = apply_package_upgrade(
                user,
                selected_package["id"],
                reference_id=reference_id,
                timestamp_iso=timestamp_iso,
                sub_type=sub_type,
                payment_type=payment_type,
            )
            status_box.update(label="Package upgrade complete.", state="complete")
            st.toast("Package upgraded")
        except Exception as exc:  # noqa: BLE001
            status_box.update(label="Upgrade failed.", state="error")
            st.error(f"Unable to apply the upgrade: {exc}")
            return

    updated_user = st.session_state.collection.find_one({"_id": user["_id"]}) or user

    try:
        calendar_result = ensure_calendar_entries(
            updated_user,
            result.get("calendar_start_date", result["start_date"]),
            result["end_date"],
        )
        if calendar_result.get("updated_days"):
            st.toast(f"Generated {calendar_result['updated_days']} star prediction day(s).")
        if calendar_result.get("basic_profile_days") or calendar_result.get("basic_holiday_days"):
            st.toast("Updated base calendar entries.")
        if calendar_result.get("gpt_triggered"):
            st.info("Background GPT calendar refresh started for this user.")
        if calendar_result.get("errors"):
            st.warning("Calendar update completed with warnings:")
            for err in calendar_result["errors"]:
                st.write(f"- {err}")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Calendar update failed: {exc}")

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
    st.json(summary, expanded=False)
