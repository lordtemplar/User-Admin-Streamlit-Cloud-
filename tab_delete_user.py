"""Danger zone: allow administrators to delete a user document."""
from __future__ import annotations

import streamlit as st


def render_delete_user_tab(user):
    st.subheader("Danger zone: delete user")
    st.warning(
        "Deleting a user removes their profile, questions, and history from the database. "
        "This action cannot be undone."
    )

    with st.form("delete_user_form"):
        confirmation = st.text_input(
            'Type "DELETE" to confirm',
            key="delete_confirm_text",
        )
        submitted = st.form_submit_button("Delete account", use_container_width=True, type="primary")

    if not submitted:
        return

    if confirmation.strip().upper() != "DELETE":
        st.warning('Confirmation text must match "DELETE".')
        return

    with st.status("Removing user document…", expanded=False) as status_box:
        try:
            result = st.session_state.collection.delete_one({"_id": user["_id"]})
            if result.deleted_count != 1:
                raise RuntimeError("User document was not removed. Please try again.")
            st.session_state.found_user = None
            st.session_state.user_questions = []
            st.session_state.selected_id = None
            st.session_state.search_results = []
            status_box.update(label="User removed.", state="complete")
            st.toast("User deleted permanently.")
        except Exception as exc:  # noqa: BLE001
            status_box.update(label="Deletion failed.", state="error")
            st.error(f"Unable to delete user: {exc}")
