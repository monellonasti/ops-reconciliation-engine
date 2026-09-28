"""Small helpers used across the engine: missing-value checks, masking, formatting.

Numbers and dates are read and shown according to the ``formats`` block of the
rules file, applied once per run through :func:`configure_formats`. Values
stored inside findings stay canonical (floats, ISO dates) so that exports and
review-history fingerprints do not depend on the display convention; only
text shown to people is localised.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- configured formats --------------------------------------------------------------


@dataclass(frozen=True)
class Formats:
    decimal_separator: str = "."
    thousands_separator: str = ","
    output_date_format: str = "%Y-%m-%d"
    input_date_formats: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y")


_formats = Formats()


def configure_formats(
    *,
    decimal_separator: str = ".",
    thousands_separator: str = ",",
    output_date_format: str = "%Y-%m-%d",
    input_date_formats: Sequence[str] = ("%Y-%m-%d", "%d/%m/%Y"),
) -> Formats:
    """Set how numbers and dates are read and shown. Returns the previous settings."""
    global _formats
    previous = _formats
    _formats = Formats(
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        output_date_format=output_date_format,
        input_date_formats=tuple(input_date_formats),
    )
    return previous


def current_formats() -> Formats:
    return _formats


def reset_formats() -> None:
    configure_formats()


# --- missing values and normalisation -------------------------------------------------


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


# --- numbers ---------------------------------------------------------------------------


def parse_number(value: Any, formats: Formats | None = None) -> float | None:
    """Read a number written with the configured separators; None when it is not one.

    Excel cells arrive as numbers already. Text such as ``2,100`` (default
    formats) or ``2.100,50`` (Italian profile) is accepted only when the
    thousands grouping is consistent, so a value written in the other
    convention is reported as invalid instead of being silently misread.
    """
    fmt = formats or _formats
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(" ", "")
    if not text:
        return None
    thousands, decimal = fmt.thousands_separator, fmt.decimal_separator
    if thousands and thousands in text:
        grouped = rf"^[+-]?\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+(?:{re.escape(decimal)}\d+)?$"
        if not re.match(grouped, text):
            return None
        text = text.replace(thousands, "")
    if decimal != ".":
        if "." in text:
            return None
        text = text.replace(decimal, ".")
    try:
        return float(text)
    except ValueError:
        return None


def percentage_change(previous: Any, current: Any, *, rounded: bool = True) -> float | None:
    """Relative change in percent, rounded to two decimals.

    Returns None when a percentage is not meaningful (missing or zero baseline).
    Use rounded=False for threshold classification; round only for display.
    """
    if is_missing(previous) or is_missing(current):
        return None
    prev = float(previous)
    curr = float(current)
    if prev == 0 or math.isinf(prev) or math.isinf(curr):
        return None
    # Decimal text avoids binary floating-point noise at exact business thresholds.
    before, after = Decimal(str(prev)), Decimal(str(curr))
    change = float((after - before) / abs(before) * 100)
    return round(change, 2) if rounded else change


# --- formatting for people -----------------------------------------------------------


def _localise_separators(text: str) -> str:
    """Turn Python's ``1,234.56`` rendering into the configured separators."""
    fmt = _formats
    if fmt.thousands_separator == "," and fmt.decimal_separator == ".":
        return text
    return (
        text.replace(",", "\x00")
        .replace(".", fmt.decimal_separator)
        .replace("\x00", fmt.thousands_separator)
    )


def format_number(number: float, decimals: int | None = None) -> str:
    """``2100`` -> ``2,100`` (or ``2.100`` with the Italian profile); two decimals when needed."""
    value = float(number)
    if decimals is None:
        decimals = 0 if value.is_integer() else 2
    return _localise_separators(f"{value:,.{decimals}f}")


def format_plain(number: float) -> str:
    """Compact rendering of a threshold: ``15`` -> ``15``, ``12.5`` -> ``12.5`` / ``12,5``."""
    return _localise_separators(f"{number:g}")


def format_date(value: datetime | date | pd.Timestamp) -> str:
    return value.strftime(_formats.output_date_format)


def format_value(value: Any) -> str:
    """Human-friendly rendering for tables and messages."""
    if is_missing(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return format_date(value)
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return format_number(float(value))
    return str(value)


def format_percentage(value: float | None) -> str:
    if value is None:
        return ""
    return _localise_separators(f"{value:+.2f}%")


def format_change(change: float, thresholds: Iterable[float]) -> str:
    """Percentage magnitude for messages: two decimals, unless that rounding would
    land exactly on a configured threshold while the true value does not.

    ``42.857142`` -> ``42.86``; ``15.0001`` with a 15% threshold -> ``15.0001``.
    """
    magnitude = abs(change)
    compact = f"{magnitude:.2f}"
    for threshold in thresholds:
        if float(compact) == float(threshold) and magnitude != float(threshold):
            return _localise_separators(f"{magnitude:.6f}".rstrip("0").rstrip("."))
    return _localise_separators(compact)


def format_timestamp(iso_text: str | None) -> str:
    """A stored UTC timestamp (``2026-09-28T19:58:04+00:00``) as local date and time
    in the configured date format, for example ``28/09/2026 21:58``."""
    if not iso_text:
        return ""
    try:
        moment = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime(f"{_formats.output_date_format} %H:%M")


def format_for_display(value: Any) -> str:
    """Render a value stored in a finding (float or ISO date string) for the UI."""
    if is_missing(value):
        return ""
    if isinstance(value, str) and _ISO_DATE.match(value):
        try:
            return format_date(datetime.strptime(value, "%Y-%m-%d"))
        except ValueError:
            return value
    return format_value(value)


def to_display_value(value: Any) -> str | float | None:
    """Coerce a cell to what an :class:`Issue` carries: floats, ISO date strings or text."""
    if is_missing(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value)


def display_value(field: str | None, value: Any, masked_fields: Iterable[str]) -> str | float | None:
    """Value as it may appear in issues, exports and the UI.

    Fields listed in ``masked_fields`` are never shown in full. IBANs keep a
    recognisable prefix and suffix; any other masked field is hidden entirely.
    """
    if is_missing(value):
        return None
    if field == "iban" or (field is not None and field in set(masked_fields)):
        return mask_iban(value) if field == "iban" else "****"
    shown = to_display_value(value)
    return redact_iban_text(shown) if isinstance(shown, str) else shown


# --- redaction -------------------------------------------------------------------------

# Recognizable compact or space-separated bank identifiers in misplaced input.
_IBAN_TEXT = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:[ \t]?[A-Za-z0-9]){11,30}(?![A-Za-z0-9])")


def redact_iban_text(text: str) -> str:
    return _IBAN_TEXT.sub(lambda match: mask_iban(match.group()) or "****", text)


def redact_message(message: str, rows: Iterable[dict[str, Any]], masked_fields: Iterable[str]) -> str:
    """Remove configured values from free text as well as structured cells."""
    replacements = set()
    for row in rows:
        for field in masked_fields:
            value = row.get(field)
            if not is_missing(value):
                replacements.add(str(value))
                replacements.add(format_value(value))
    for value in sorted(replacements, key=len, reverse=True):
        if value:
            message = message.replace(value, "****")
    return redact_iban_text(message)
