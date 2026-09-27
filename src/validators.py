"""Single-dataset checks: value types, required fields, duplicates and invalid values.

These checks look at one cycle in isolation. They also produce the *typed*
frame (numbers as floats, dates as timestamps) that the cross-cycle
reconciliation works on.

Rule functions receive rows as plain dicts (one conversion per dataset)
rather than indexing into the DataFrame per row, which keeps runs on large
exports in the seconds rather than minutes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime
from typing import Any, Literal

import pandas as pd

from src.config import Rules
from src.i18n import t
from src.loader import LoadedDataset
from src.models import (
    DATE_FIELDS,
    KEY_FIELD,
    NUMERIC_FIELDS,
    SOURCE_ROW,
    Category,
    Issue,
    Severity,
)
from src.utils import (
    display_value,
    format_value,
    is_missing,
    is_valid_email,
    normalize_iban,
    normalize_text,
    parse_number,
    redact_message,
)

Row = dict[str, Any]


@dataclass
class ValidatedDataset:
    name: Literal["previous", "current"]
    frame: pd.DataFrame
    issues: list[Issue] = dataclass_field(default_factory=list)
    missing_columns: set[str] = dataclass_field(default_factory=set)

    @property
    def record_count(self) -> int:
        return len(self.frame)

    @property
    def records(self) -> list[Row]:
        return self.frame.to_dict("records")


def validate_dataset(loaded: LoadedDataset, rules: Rules) -> ValidatedDataset:
    """Run every single-dataset check and return the typed frame plus its issues."""
    raw = loaded.frame
    typed = raw.copy()
    issues: list[Issue] = []
    issues += coerce_numeric_columns(typed, loaded.name, rules)
    issues += coerce_date_columns(typed, loaded.name, rules)
    # Required-field and duplicate checks run on the raw rows so an unparseable
    # number is reported once (as invalid), not twice (invalid and missing).
    raw_rows = raw.to_dict("records")
    issues += check_required_fields(raw_rows, loaded.name, rules)
    issues += check_duplicates(raw_rows, loaded.name, rules)
    issues += check_value_ranges(typed.to_dict("records"), loaded.name, rules)
    return ValidatedDataset(
        name=loaded.name, frame=typed, issues=issues, missing_columns=loaded.missing_columns
    )


class IssueFactory:
    """Builds issues for one dataset so call sites only state what is wrong."""

    def __init__(self, dataset: Literal["previous", "current"], rules: Rules):
        self.dataset = dataset
        self.rules = rules

    def issue(
        self,
        row: Row,
        *,
        category: Category,
        rule: str,
        severity: Severity,
        message: str,
        field: str | None = None,
        value: Any = None,
        requires_review: bool | None = None,
    ) -> Issue:
        shown = display_value(field, value, self.rules.masked_fields)
        values = {"current_value": shown} if self.dataset == "current" else {"previous_value": shown}
        return Issue(
            employee_id=normalize_text(row.get(KEY_FIELD)),
            row_number=int(row[SOURCE_ROW]) if SOURCE_ROW in row else None,
            dataset=self.dataset,
            category=category,
            field=field,
            rule=rule,
            severity=severity,
            requires_review=self.rules.requires_review(severity, requires_review),
            message=redact_message(message, [row], self.rules.masked_fields),
            **values,
        )


# --- type coercion -----------------------------------------------------------


def coerce_numeric_columns(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    """Convert numeric columns in place; report cells that are not numbers."""
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for column in NUMERIC_FIELDS:
        if column not in frame.columns:
            continue
        raw = frame[column]
        numeric = pd.to_numeric(raw.map(parse_number), errors="coerce")
        invalid = raw.notna() & ~numeric.map(_is_finite)
        for row in frame.loc[invalid].to_dict("records"):
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field=column,
                    rule="invalid_number",
                    severity=rules.invalid_values.severity,
                    value=row[column],
                    message=t("validators.invalid_number", column=column),
                )
            )
        frame[column] = numeric.mask(invalid).astype("float64")
    return issues


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(value)
    except TypeError:
        return False


def parse_dates(raw: pd.Series, formats: Sequence[str]) -> pd.Series:
    """Try each configured text format; cells that already are dates (Excel) pass through."""
    already = raw.map(lambda v: isinstance(v, (datetime, date)))
    text = raw.where(~already)
    parsed: pd.Series | None = None
    for pattern in formats:
        attempt = pd.to_datetime(text, format=pattern, errors="coerce")
        parsed = attempt if parsed is None else parsed.fillna(attempt)
    assert parsed is not None  # formats is never empty (validated in the rules)
    if already.any():
        parsed = parsed.fillna(pd.to_datetime(raw.where(already), errors="coerce"))
    return parsed


def coerce_date_columns(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    """Convert date columns in place; report cells that are not valid dates."""
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    formats = rules.formats.input_date_formats
    for column in DATE_FIELDS:
        if column not in frame.columns:
            continue
        raw = frame[column]
        parsed = parse_dates(raw, formats)
        invalid = raw.notna() & parsed.isna()
        for row in frame.loc[invalid].to_dict("records"):
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field=column,
                    rule="invalid_date",
                    severity=rules.invalid_values.severity,
                    value=row[column],
                    message=t(
                        "validators.invalid_date",
                        column=column,
                        value=row[column],
                        formats=" / ".join(formats),
                    ),
                )
            )
        frame[column] = parsed
    return issues


# --- required fields ---------------------------------------------------------


def check_required_fields(rows: list[Row], dataset: str, rules: Rules) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    if not rows:
        return issues
    columns = [column for column in rules.required_fields if column in rows[0]]
    for row in rows:
        for column in columns:
            if not is_missing(row[column]):
                continue
            message = (
                t("validators.missing_key")
                if column == KEY_FIELD
                else t("validators.missing_field", column=column)
            )
            issues.append(
                factory.issue(
                    row,
                    category=Category.MISSING_DATA,
                    field=column,
                    rule="missing_required_field",
                    severity=rules.missing_data.severity,
                    message=message,
                )
            )
    return issues


# --- duplicates ----------------------------------------------------------------


def check_duplicates(rows: list[Row], dataset: str, rules: Rules) -> list[Issue]:
    issues: list[Issue] = []
    issues += _duplicate_keys(rows, dataset, rules)
    issues += _duplicate_values(
        rows,
        dataset,
        rules,
        column="email",
        normalize=lambda value: (normalize_text(value) or "").lower() or None,
        severity=rules.duplicates.email,
    )
    issues += _duplicate_values(
        rows,
        dataset,
        rules,
        column="iban",
        normalize=normalize_iban,
        severity=rules.duplicates.iban,
    )
    return issues


def _group_rows(
    rows: list[Row], column: str, normalize: Callable[[Any], str | None]
) -> dict[str, list[Row]]:
    """Rows sharing the same normalized value, only for values seen more than once."""
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        key = normalize(row.get(column))
        if key is not None:
            groups[key].append(row)
    return {key: group for key, group in groups.items() if len(group) > 1}


def _duplicate_keys(rows: list[Row], dataset: str, rules: Rules) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for key, group in _group_rows(rows, KEY_FIELD, normalize_text).items():
        row_list = ", ".join(str(row[SOURCE_ROW]) for row in group)
        issues.append(
            factory.issue(
                group[0],
                category=Category.DUPLICATE,
                field=KEY_FIELD,
                rule="duplicate_employee_id",
                severity=rules.duplicates.employee_id,
                requires_review=True,
                value=key,
                message=t("validators.duplicate_key", key=key, count=len(group), rows=row_list),
            )
        )
    return issues


def _duplicate_values(
    rows: list[Row],
    dataset: str,
    rules: Rules,
    *,
    column: str,
    normalize: Callable[[Any], str | None],
    severity: Severity,
) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for group in _group_rows(rows, column, normalize).values():
        if len({_label(row) for row in group}) < 2:
            continue  # the same record exported twice: already a duplicate-key issue
        for row in group:
            others = sorted({_label(other) for other in group if _label(other) != _label(row)})
            issues.append(
                factory.issue(
                    row,
                    category=Category.DUPLICATE,
                    field=column,
                    rule=f"duplicate_{column}",
                    severity=severity,
                    value=row[column],
                    message=t("validators.duplicate_value", column=column, others=", ".join(others)),
                )
            )
    return issues


def _label(row: Row) -> str:
    key = normalize_text(row.get(KEY_FIELD))
    return key if key else t("record.row", line=row[SOURCE_ROW])


# --- value ranges --------------------------------------------------------------


def check_value_ranges(rows: list[Row], dataset: str, rules: Rules) -> list[Issue]:
    """Values that parse fine but cannot be right. Expects typed rows."""
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    severity = rules.invalid_values.severity
    issues: list[Issue] = []
    for row in rows:
        salary = row.get("monthly_salary")
        if not is_missing(salary) and salary < 0:
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field="monthly_salary",
                    rule="negative_salary",
                    severity=severity,
                    value=salary,
                    message=t("validators.negative_salary"),
                )
            )

        start, end = row.get("start_date"), row.get("end_date")
        if not is_missing(start) and not is_missing(end) and end < start:
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field="end_date",
                    rule="end_before_start",
                    severity=severity,
                    value=end,
                    message=t(
                        "validators.end_before_start", end=format_value(end), start=format_value(start)
                    ),
                )
            )

        email = row.get("email")
        if not is_missing(email) and not is_valid_email(email):
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field="email",
                    rule="malformed_email",
                    severity=rules.invalid_values.malformed_email_severity,
                    value=email,
                    message=t("validators.malformed_email", email=email),
                )
            )
    return issues
