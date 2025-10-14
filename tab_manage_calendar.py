"""Calendar management tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.calendar import ensure_calendar_entries
from um_utils import get_user_type, refresh_current_user


def render_manage_calendar_tab(user):
    st.subheader("Review calendar predictions")

    if get_user_type(user) != "mu insight":
        st.warning("Calendar management is available only for mu insight users.")
        return

    predictions_gpt = user.get("period_predictions_gpt") or {}
    predictions_std = user.get("period_predictions") or {}
    combined_dates = sorted(set(predictions_gpt.keys()) | set(predictions_std.keys()))

    if not combined_dates:
        st.info("This user has no stored calendar predictions yet.")
    else:
        rows = []
        for date_str in combined_dates:
            std_predictions = predictions_std.get(date_str, {})
            std_text = ", ".join(
                str(result.get("start_thai", "")) for result in std_predictions.values()
            )
            gpt_detail = predictions_gpt.get(date_str, {})
            gpt_text = ""
            if g_detail := gpt_detail:
                day_name = g_detail.get("day_name", "")
                theme = g_detail.get("theme", "")
                gpt_text = f"{day_name} ({theme})".strip(" ()")

            rows.append(
                {
                    "Date": date_str,
                    "Standard": std_text,
                    "GPT Summary": gpt_text,
                }
            )

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    period_info = user.get("period_available") or {}
    start_date = period_info.get("start_date")
    end_date = period_info.get("end_date")

    if st.button("Rebuild calendar predictions", use_container_width=True):
        if not (start_date and end_date):
            st.warning("The user does not have a valid mu insight period to rebuild from.")
            return

        with st.status("Updating calendar entries...", expanded=False) as status_box:
            try:
                result = ensure_calendar_entries(user, start_date, end_date)
                status_box.update(label="Calendar rebuild complete.", state="complete")
                updated_days = result.get("updated_days", 0)
                if updated_days:
                    st.toast(f"Generated {updated_days} prediction day(s).")
                if result.get("errors"):
                    st.warning("Calendar rebuild completed with warnings:")
                    for err in result["errors"]:
                        st.write(f"- {err}")
                refresh_current_user()
            except Exception as exc:  # noqa: BLE001
                status_box.update(label="Calendar rebuild failed.", state="error")
                st.error(f"Unable to rebuild calendar entries: {exc}")
