from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Dict, Any

import pandas as pd
from pymongo import MongoClient

import config


def _calendar_client():
    return MongoClient(config.MONGO_URI)


@lru_cache(maxsize=24)
def load_calendar_profile_month(year: int, month: int) -> Dict[str, Any]:
    collection_name = f"calendar_profiles_{year + 543}"
    with _calendar_client() as client:
        db = client["your_database"]
        collection = db[collection_name]

        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        results = list(collection.find({"date": {"$gte": start, "$lt": end}}))
        if not results:
            return {}

        df = pd.DataFrame(results)
        if "_id" in df.columns:
            df.drop(columns=["_id"], inplace=True)
        df = df.replace([float("inf"), float("-inf")], pd.NA).fillna("")
        df = df.astype(str)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df.set_index("date").to_dict(orient="index")


@lru_cache(maxsize=24)
def load_calendar_holiday_month(year: int, month: int) -> Dict[str, Any]:
    collection_name = "calendar_holidays_until2025_2"
    with _calendar_client() as client:
        db = client["your_database"]
        collection = db[collection_name]

        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        results = list(collection.find({"date": {"$gte": start, "$lt": end}}))
        if not results:
            return {}

        df = pd.DataFrame(results)
        if "_id" in df.columns:
            df.drop(columns=["_id"], inplace=True)
        df = df.replace([float("inf"), float("-inf")], pd.NA).fillna("")
        df = df.astype(str).drop_duplicates(subset=["date"])
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df.set_index("date").to_dict(orient="index")


def get_general_calendar(year: int, month: int) -> Dict[str, Dict[str, Any]]:
    profiles = load_calendar_profile_month(year, month)
    holidays = load_calendar_holiday_month(year, month)
    return {"profile": profiles, "holiday": holidays}
