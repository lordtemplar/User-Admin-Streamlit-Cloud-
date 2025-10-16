"""Streamlit entry point for the User Admin console."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import config  # noqa: E402
from search_display import render_search_and_results  # noqa: E402
from tab_delete_user import render_delete_user_tab  # noqa: E402
from tab_edit_user import render_edit_user_tab  # noqa: E402
from tab_manage_calendar import render_manage_calendar_tab  # noqa: E402
from tab_manage_questions import render_manage_questions_tab  # noqa: E402
from tab_upgrade_user import render_upgrade_user_tab  # noqa: E402
from um_utils import ensure_session, get_db  # noqa: E402


st.set_page_config(page_title="User Admin", layout="wide", initial_sidebar_state="collapsed")
st.title("User Admin Console")

ensure_session()

with st.status("Connecting to MongoDB...", expanded=False) as status_box:
    try:
        db, client = get_db()
        st.session_state.collection = db[config.COLL_NAME]
        st.session_state.collection_questions = db[config.COLL_QUESTIONS_NAME]
        st.session_state.collection_transactions = db.get_collection("transactions")
        st.session_state.mongo_client = client
        st.session_state.connected = True
        status_box.update(label="MongoDB connection established.", state="complete")
        st.toast("Connected to MongoDB")
    except Exception as exc:  # noqa: BLE001
        st.session_state.connected = False
        status_box.update(label="Failed to connect to MongoDB.", state="error")
        st.error(f"Unable to connect to MongoDB: {exc}")
        st.stop()


render_search_and_results()

user = st.session_state.get("found_user")
if user:
    tab_labels = [
        "Edit Profile",
        "Upgrade Package",
        "Manage Custom Questions",
        "Manage Calendar",
        "Delete User",
    ]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        render_edit_user_tab(user)
    with tabs[1]:
        render_upgrade_user_tab(user)
    with tabs[2]:
        render_manage_questions_tab()
    with tabs[3]:
        render_manage_calendar_tab(user)
    with tabs[4]:
        render_delete_user_tab(user)
else:
    st.info("Search for a user and load their profile to access management actions.")
