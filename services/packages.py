from __future__ import annotations

from typing import Dict, List


PACKAGES: Dict[str, Dict[str, int | float | str]] = {
    "demo": {
        "title": "Demo Package",
        "description": "Access mu insight for 3 days and receive 3 tokens.",
        "price": 0,
        "tokens": 3,
        "duration": 0,
        "duration_days": 3,
    },
    "1": {
        "title": "Monthly Package",
        "description": "One month of mu insight access with 4 additional tokens.",
        "price": 359,
        "tokens": 4,
        "duration": 1,
        "duration_days": 0,
    },
    "2": {
        "title": "Quarterly Package",
        "description": "Three months of mu insight access with 12 additional tokens.",
        "price": 999,
        "tokens": 12,
        "duration": 3,
        "duration_days": 0,
    },
    "3": {
        "title": "Semi-Annual Package",
        "description": "Six months of mu insight access with 24 additional tokens.",
        "price": 1859,
        "tokens": 24,
        "duration": 6,
        "duration_days": 0,
    },
    "4": {
        "title": "Annual Package",
        "description": "Twelve months of mu insight access with 48 additional tokens.",
        "price": 3359,
        "tokens": 48,
        "duration": 12,
        "duration_days": 0,
    },
    "6": {
        "title": "Single Token",
        "description": "Add one extra token to the current balance.",
        "price": 59,
        "tokens": 1,
        "duration": 0,
        "duration_days": 0,
    },
    "7": {
        "title": "Ten Tokens",
        "description": "Add ten extra tokens to the current balance.",
        "price": 490,
        "tokens": 10,
        "duration": 0,
        "duration_days": 0,
    },
}

PACKAGE_ORDER = ["demo", "1", "2", "3", "4", "6", "7"]


def list_packages() -> List[Dict[str, int | float | str]]:
    """Return all packages in the preferred order."""
    items: List[Dict[str, int | float | str]] = []
    for key in PACKAGE_ORDER:
        pkg = PACKAGES.get(key)
        if pkg:
            item = dict(pkg)
            item["id"] = key
            items.append(item)
    return items


def get_package(package_key: str) -> Dict[str, int | float | str]:
    """Return a single package definition."""
    pkg = PACKAGES.get(package_key)
    if not pkg:
        raise KeyError(f"Unknown package id: {package_key}")
    item = dict(pkg)
    item["id"] = package_key
    return item
