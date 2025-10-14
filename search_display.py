"""Search utilities and result rendering for the User Admin console."""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from um_utils import as_int, get_user_type, load_user_data


SearchResult = Dict[str, Any]


def _trigger_search() -> None:
    st.session_state.kw_submit = (st.session_state.kw or "").strip()
    st.session_state.do_search = True
    st.session_state.selected_id = None
    st.session_state.found_user = None
    st.session_state.user_questions = []


def _ensure_collection() -> bool:
    if not st.session_state.get("connected"):
        st.error("The database connection is not ready yet.")
        return False
    if "collection" not in st.session_state:
        st.error("MongoDB collection handle is missing from the session.")
        return False
    return True


def _run_search(keyword: str) -> List[SearchResult]:
    query = {"user_profiles": {"$regex": keyword, "$options": "i"}}
    collection = st.session_state.collection
    results = list(collection.find(query, limit=200))
    st.session_state.search_results = results
    return results


def render_search_and_results() -> None:
    """Render search form, results table, and user selection controls."""
    st.subheader("Search for users")

    st.text_input(
        "LINE display name",
        key="kw",
        placeholder="Enter part of the LINE display name",
        on_change=_trigger_search,
    )
    st.button("Search", use_container_width=True, on_click=_trigger_search)

    if st.session_state.do_search:
        if not st.session_state.kw_submit:
            st.info("Please provide a keyword before running a search.")
        elif _ensure_collection():
            keyword = st.session_state.kw_submit
            with st.status(f"Searching for '{keyword}'...", expanded=False) as status_box:
                try:
                    results = _run_search(keyword)
                    if results:
                        status_box.update(label=f"Found {len(results)} user(s).", state="complete")
                    else:
                        status_box.update(label="No users matched that query.", state="complete")
                except Exception as exc:  # noqa: BLE001
                    status_box.update(label="Search failed.", state="error")
                    st.error(f"Unable to fetch results: {exc}")
        st.session_state.do_search = False

    results = st.session_state.get("search_results", [])
    if not results:
        return

    dataframe_rows: List[Dict[str, Any]] = []
    backend_rows: List[Dict[str, str]] = []
    for doc in results:
        doc_id = str(doc.get("_id"))
        name = str(doc.get("user_profiles", ""))
        dataframe_rows.append(
            {
                "LINE Name": name,
                "LINE ID": str(doc.get("line_id", "")),
                "Tokens": as_int(doc.get("user_question_left", 0)),
                "User Type": get_user_type(doc),
            }
        )
        backend_rows.append({"doc_id": doc_id, "name": name})

    st.dataframe(pd.DataFrame(dataframe_rows), hide_index=True, use_container_width=True)

    if not backend_rows:
        return

    previous_index = 0
    selected_id = st.session_state.get("selected_id")
    if selected_id:
        for idx, row in enumerate(backend_rows):
            if row["doc_id"] == selected_id:
                previous_index = idx
                break

    names = [row["name"] or f"User {idx + 1}" for idx, row in enumerate(backend_rows)]
    selected_idx = st.selectbox(
        "Pick a user to load",
        options=list(range(len(backend_rows))),
        index=previous_index,
        format_func=lambda idx: names[idx],
    )
    chosen_row = backend_rows[selected_idx]

    if st.button("Load user profile", type="primary", use_container_width=True):
        doc_id = chosen_row.get("doc_id")
        display_name = chosen_row.get("name") or "selected user"
        if doc_id:
            with st.status(f"Loading data for {display_name}...", expanded=False) as status_box:
                success, message = load_user_data(doc_id)
                if success:
                    status_box.update(label="User loaded.", state="complete")
                    st.toast("User profile loaded")
                else:
                    status_box.update(label="Failed to load user.", state="error")
                    st.error(message)
        else:
            st.warning("Unable to resolve the selected user. Try searching again.")
