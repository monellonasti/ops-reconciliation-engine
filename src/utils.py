"""Small helpers used across the engine: missing-value checks, masking, formatting."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

import pandas as pd

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_missing(value: Any) -> bool:
    """True for None, NaN/NaT and blank strings."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_text(value: Any) -> str | None:
    """Trim whitespace; blank becomes None."""
    if is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_iban(value: Any) -> str | None:
    """Canonical form for comparison: no spaces, upper case."""
    text = normalize_text(value)
    if text is None:
        return None
    return re.sub(r"\s+", "", text).upper()


def mask_iban(value: Any) -> str | None:
    """Hide the middle of an IBAN: ``IT60X0542811101000000123456`` -> ``IT60X****3456``.

    Short or odd-looking values are fully masked rather than partially revealed.
    """
    iban = normalize_iban(value)
    if iban is None:
        return None
    if len(iban) < 12:
        return "****"
    return f"{iban[:5]}****{iban[-4:]}"


def is_valid_email(value: Any) -> bool:
    text = normalize_text(value)
    return text is not None and _EMAIL_PATTERN.match(text) is not None


def percentage_change(previous: Any, current: Any) -> float | None:
    """Relative change in percent, rounded to two decimals.

    Returns None when a percentage is not meaningful (missing or zero baseline).
    """
    if is_missing(previous) or is_missing(current):
        return None
    prev = float(previous)
    curr = float(current)
    if prev == 0 or math.isinf(prev) or math.isinf(curr):
        return None
    return round((curr - prev) / abs(prev) * 100, 2)


def format_value(value: Any) -> str:
    """Human-friendly rendering for tables and messages."""
    if is_missing(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}"
    return str(value)


def format_percentage(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:+.2f}%"


def to_display_value(value: Any) -> str | float | None:
    """Coerce a cell to something an :class:`Issue` can carry (str, float or None)."""
    if is_missing(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return format_value(value)
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)
