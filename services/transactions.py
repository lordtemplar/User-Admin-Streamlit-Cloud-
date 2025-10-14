from __future__ import annotations

from typing import Dict, Any

import streamlit as st
from datetime import datetime


def record_transaction(
    *,
    user: Dict[str, Any],
    package: Dict[str, Any],
    reference_id: str,
    timestamp_iso: str,
    sub_type: str,
    payment_type: str,
) -> None:
    collection = st.session_state.get("collection_transactions")
    if collection is None:
        return

    line_id = user.get("line_id")
    doc = {
        "userId": line_id,
        "line_id": line_id,
        "packageId": package.get("id"),
        "packageTitle": package.get("title"),
        "price": package.get("price"),
        "tokens": package.get("tokens"),
        "duration": package.get("duration", 0),
        "duration_days": package.get("duration_days", 0),
        "subType": sub_type,
        "paymentType": payment_type,
        "timestamp": timestamp_iso,
        "referenceId": reference_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    collection.insert_one(doc)
