"""Profile editing tab."""
from __future__ import annotations

import streamlit as st

from um_utils import as_int, get_user_type, refresh_current_user


def render_edit_user_tab(user):
    st.subheader("Edit user profile")
    st.write(f"**LINE ID:** {user.get('line_id', 'N/A')}")
    st.write(f"**Current package:** {get_user_type(user)}")

    with st.form("edit_user_form"):
        new_name = st.text_input("LINE display name", value=user.get("user_profiles", ""))
        new_token = st.number_input(
            "Remaining tokens",
            min_value=0,
            step=1,
            value=as_int(user.get("user_question_left", 0)),
        )
        submitted = st.form_submit_button("Save changes", type="primary")

    if not submitted:
        return

    if not new_name.strip():
        st.warning("Display name cannot be blank.")
        return

    with st.status("Updating user…", expanded=False) as status_box:
        try:
            st.session_state.collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"user_profiles": new_name.strip(), "user_question_left": int(new_token)}},
            )
            refresh_current_user()
            status_box.update(label="User updated.", state="complete")
            st.toast("User profile updated", icon="✅")
        except Exception as exc:  # noqa: BLE001
            status_box.update(label="Update failed.", state="error")
            st.error(f"Unable to update user: {exc}")
