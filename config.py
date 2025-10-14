"""Central configuration helpers for the Streamlit deployment.

Values are resolved in the following order:
1. Streamlit secrets (supports dotted keys such as ``mongo.uri``).
2. Environment variables (upper-case with dots replaced by underscores).
3. Optional default supplied by the caller.

Raise a ``RuntimeError`` when a required value is missing so the app fails fast
with a clear message instead of producing obscure downstream errors.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Mapping

try:  # Streamlit is only available at runtime; keep import optional for tests.
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - executed only outside Streamlit
    st = None  # type: ignore


def _resolve_streamlit_secrets() -> Mapping[str, Any]:
    if st is None:
        return {}
    try:
        return st.secrets  # type: ignore[return-value]
    except (AttributeError, RuntimeError):
        # AttributeError: secrets not initialised yet (e.g. unit tests).
        # RuntimeError: running outside a Streamlit script.
        return {}


@lru_cache(maxsize=1)
def _cached_secrets() -> Mapping[str, Any]:
    return _resolve_streamlit_secrets()


def _pluck(mapping: Mapping[str, Any], dotted_key: str) -> Any:
    current: Any = mapping
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def get_setting(dotted_key: str, default: Any = None, *, required: bool = False, env_key: str | None = None) -> Any:
    """
    Retrieve a configuration value.

    Parameters
    ----------
    dotted_key:
        Key for Streamlit secrets (dot notation supported).
    default:
        Fallback value when neither secrets nor environment provide a value.
    required:
        When True, raise RuntimeError if the value resolves to falsy.
    env_key:
        Optional explicit environment variable name. Defaults to upper-case
        dotted_key with dots replaced by underscores.
    """
    secrets = _cached_secrets()
    value = _pluck(secrets, dotted_key) if secrets else None

    if value in (None, ""):
        env_name = env_key or dotted_key.replace(".", "_").upper()
        value = os.getenv(env_name, default)

    if required and (value is None or value == ""):
        raise RuntimeError(
            f"Missing configuration value: {dotted_key} "
            f"(env: {env_key or dotted_key.replace('.', '_').upper()})"
        )

    return value


MONGO_URI: str = get_setting("mongo.uri", required=True)
DB_NAME: str = get_setting("mongo.db_name", default="users")
COLL_NAME: str = get_setting("mongo.collection", default="user_profiles")
COLL_QUESTIONS_NAME: str = get_setting("mongo.questions_collection", default="questions")

API_BASE_URL: str = get_setting("api.base_url", default="https://api.spmu.me")
STAR_PREDICT_URL: str = get_setting("api.star_predict_url", default=f"{API_BASE_URL}/api/api5_star_predict")

# Legacy compatibility for shared utilities.
MONGO_URL: str = get_setting("mongo.url", default=MONGO_URI)
GPT_URL: str = get_setting("gpt.url", default="https://api.openai.com/v1/chat/completions")
GPT_API_KEY: str = get_setting("gpt.api_key", default="", required=False)
