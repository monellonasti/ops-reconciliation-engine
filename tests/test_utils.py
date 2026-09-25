"""Helpers: masking, percentage change, formatting and value display."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.utils import (
    display_value,
    format_percentage,
    format_value,
    is_missing,
    is_valid_email,
    mask_iban,
    percentage_change,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("IT60X0542811101000000123456", "IT60X****3456"),
        ("it60 x054 2811 1010 0000 0123 456", "IT60X****3456"),
        ("DE89370400440532013000", "DE893****3000"),
        ("SHORT", "****"),  # too short to reveal anything safely
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_mask_iban(raw, expected):
    assert mask_iban(raw) == expected


def test_masked_iban_never_contains_the_middle_digits():
    iban = "IT60X0542811101000000123456"
    assert "0542811101000000" not in mask_iban(iban)


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (2100, 3000, 42.86),
        (3000, 2100, -30.0),
        (2000, 2000, 0.0),
        (0, 100, None),
        (None, 100, None),
        (100, None, None),
        (float("nan"), 100, None),
        (-100, -50, 50.0),
    ],
)
def test_percentage_change(previous, current, expected):
    assert percentage_change(previous, current) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (float("nan"), ""),
        (pd.NaT, ""),
        (2100.0, "2,100"),
        (2100.5, "2,100.50"),
        (40, "40"),
        (pd.Timestamp("2024-12-31"), "2024-12-31"),
        ("full_time", "full_time"),
    ],
)
def test_format_value(value, expected):
    assert format_value(value) == expected


def test_format_percentage():
    assert format_percentage(42.857) == "+42.86%"
    assert format_percentage(-10.0) == "-10.00%"
    assert format_percentage(None) == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("", True), ("  ", True), (float("nan"), True), (pd.NaT, True), (0, False), ("x", False)],
)
def test_is_missing(value, expected):
    assert is_missing(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ada.rossi@example.com", True),
        ("a@b.co", True),
        ("ada.rossi-at-example.com", False),
        ("ada@", False),
        ("@example.com", False),
        ("ada rossi@example.com", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_email(value, expected):
    assert is_valid_email(value) is expected


def test_display_value_masks_configured_fields_only():
    masked = ["iban"]
    assert display_value("iban", "IT60X0542811101000000123456", masked) == "IT60X****3456"
    assert display_value("email", "ada@example.com", masked) == "ada@example.com"
    assert display_value("monthly_salary", 2100, masked) == 2100.0
    assert display_value("iban", None, masked) is None
    assert display_value("email", "ada@example.com", ["email"]) == "****"
    assert display_value("start_date", pd.Timestamp("2024-01-31"), masked) == "2024-01-31"
    assert math.isnan(float("nan"))  # sanity: NaN inputs are treated as missing above


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (42.857142857, "42.86"),
        (-10.0, "10.00"),
        (15.0, "15.00"),  # exactly on the threshold: nothing to disambiguate
        (15.0001, "15.0001"),  # would read as 15.00 and look like INFO
        (29.999, "29.999"),
        (30.00004, "30.00004"),
        (100.0, "100.00"),
    ],
)
def test_format_change_keeps_precision_only_near_thresholds(change, expected):
    from src.utils import format_change

    assert format_change(change, (15, 30)) == expected
