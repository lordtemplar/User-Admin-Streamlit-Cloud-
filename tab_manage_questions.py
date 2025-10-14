"""Custom question management tab."""
from __future__ import annotations

from typing import List

from bson.objectid import ObjectId
import pandas as pd
import streamlit as st

from um_utils import refresh_current_user


def render_manage_questions_tab():
    st.subheader("Manage stored questions for this user")

    questions_data: List[dict] = st.session_state.get("user_questions", [])
    if not questions_data:
        st.info("This user has no custom questions yet.")
        return

    df = pd.DataFrame(questions_data)
    df["remove"] = False

    edited_df = st.data_editor(
        df,
        column_order=("remove", "question"),
        column_config={
            "remove": st.column_config.CheckboxColumn("Remove?", default=False),
            "question": st.column_config.TextColumn("Question text"),
        },
        hide_index=True,
    )

    to_delete_ids = edited_df[edited_df["remove"]]["id"].tolist()
    if to_delete_ids:
        st.info(f"Selected {len(to_delete_ids)} question(s) for deletion.")
    else:
        st.info("Select questions above and click delete to remove them.")

    if st.button("Delete selected questions", use_container_width=True, disabled=not to_delete_ids):
        ids = [ObjectId(value) for value in to_delete_ids]
        with st.status(f"Deleting {len(ids)} question(s)...", expanded=False) as status_box:
            try:
                result = st.session_state.collection_questions.delete_many({"_id": {"$in": ids}})
                st.session_state.collection.update_one(
                    {"_id": ObjectId(st.session_state.selected_id)},
                    {"$inc": {"user_question_left": result.deleted_count}},
                )
                status_box.update(label="Questions deleted.", state="complete")
                st.toast(f"Removed {result.deleted_count} question(s).")
                refresh_current_user()
            except Exception as exc:  # noqa: BLE001
                status_box.update(label="Deletion failed.", state="error")
                st.error(f"Unable to delete questions: {exc}")
