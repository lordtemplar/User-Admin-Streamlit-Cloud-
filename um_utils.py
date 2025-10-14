"""Utility helpers shared across Streamlit tabs."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

from bson.objectid import ObjectId
from pymongo import MongoClient
import streamlit as st

import config


@st.cache_resource(show_spinner=False)
def get_db() -> Tuple[Any, MongoClient]:
    """Establish and cache the MongoDB connection."""
    if not config.MONGO_URI:
        raise RuntimeError("MONGO_URI is empty. Provide it via Streamlit secrets or environment variables.")
    client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=4000)
    client.admin.command("ping")
    db = client[config.DB_NAME]
    return db, client


def ensure_session() -> None:
    """Initialise Streamlit session state with the keys our UI expects."""
    defaults = {
        "kw": "",
        "kw_submit": "",
        "do_search": False,
        "search_results": [],
        "selected_id": None,
        "found_user": None,
        "connected": False,
        "user_questions": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def now_iso_ms_z() -> str:
    """Return the current UTC time in ISO 8601 with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def gen_reference_id() -> str:
    """Generate an opaque reference identifier."""
    digits = "".join(secrets.choice(string.digits) for _ in range(11))
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return f"Ref{digits}{suffix}"


def as_int(value: Any, default: int = 0) -> int:
    """Best-effort conversion to ``int`` with fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def get_user_type(doc: Dict[str, Any]) -> str:
    """Infer the user type from the history log."""
    history = doc.get("history_log") or []
    first_entry = history[0] if history else None
    if isinstance(first_entry, dict):
        if str(first_entry.get("subType", "")).strip().lower() == "standard":
            return "mu insight"
    return "basic"


def _fetch_user_questions(line_id: str, collection) -> Iterable[Dict[str, Any]]:
    cursor = collection.find({"line_id": line_id})
    for doc in cursor:
        dict_prompt = doc.get("dict_prompt") or {}
        question_text = dict_prompt.get("question", "N/A")
        yield {"id": str(doc["_id"]), "question": question_text}


def load_user_data(doc_id: str) -> Tuple[bool, str]:
    """Load a user document and associated questions into session state."""
    try:
        collection = st.session_state.collection
        questions_collection = st.session_state.collection_questions
    except KeyError as exc:
        return False, f"Session state is missing required key: {exc}"

    try:
        object_id = ObjectId(doc_id)
    except Exception:
        return False, "Invalid document identifier."

    user = collection.find_one({"_id": object_id})
    if not user:
        return False, "User not found."

    st.session_state.selected_id = doc_id
    st.session_state.found_user = user

    if user.get("line_id"):
        st.session_state.user_questions = list(_fetch_user_questions(user["line_id"], questions_collection))
    else:
        st.session_state.user_questions = []

    return True, "User loaded."


def refresh_current_user() -> Tuple[bool, str]:
    """Reload active user data and re-run the latest search query."""
    collection = st.session_state.get("collection")
    if collection is None:
        return False, "MongoDB collection not available yet."

    selected_id = st.session_state.get("selected_id")
    if selected_id:
        load_user_data(selected_id)

    keyword = (st.session_state.get("kw_submit") or "").strip()
    if keyword:
        try:
            st.session_state.search_results = list(
                collection.find({"user_profiles": {"$regex": keyword, "$options": "i"}}, limit=200)
            )
        except Exception as exc:  # noqa: BLE001
            return False, f"Unable to refresh search results: {exc}"

    return True, "Refreshed."
