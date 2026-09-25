"""Single-dataset checks: value types, required fields, duplicates and invalid values.

These checks look at one cycle in isolation. They also produce the *typed*
frame (numbers as floats, dates as timestamps) that the cross-cycle
reconciliation works on.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import pandas as pd

from src.config import Rules
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
    is_missing,
    is_valid_email,
    normalize_iban,
    normalize_text,
)

Row = dict[str, Any]


@dataclass
class ValidatedDataset:
    name: Literal["previous", "current"]
    frame: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.frame)


def validate_dataset(loaded: LoadedDataset, rules: Rules) -> ValidatedDataset:
    """Run every single-dataset check and return the typed frame plus its issues."""
    raw = loaded.frame
    typed = raw.copy()
    issues: list[Issue] = []
    issues += coerce_numeric_columns(typed, loaded.name, rules)
    issues += coerce_date_columns(typed, loaded.name, rules)
    # Required-field checks run on the raw frame so an unparseable number is
    # reported once (as invalid), not twice (invalid and missing).
    issues += check_required_fields(raw, loaded.name, rules)
    issues += check_duplicates(raw, loaded.name, rules)
    issues += check_value_ranges(typed, loaded.name, rules)
    return ValidatedDataset(name=loaded.name, frame=typed, issues=issues)


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
            message=message,
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
        numeric = pd.to_numeric(raw, errors="coerce")
        invalid = raw.notna() & numeric.isna()
        for row in frame.loc[invalid].to_dict("records"):
            issues.append(
                factory.issue(
                    row,
                    category=Category.INVALID_VALUE,
                    field=column,
                    rule="invalid_number",
                    severity=rules.invalid_values.severity,
                    value=row[column],
                    message=f"{column} has a non-numeric value '{row[column]}'.",
                )
            )
        frame[column] = numeric.astype("float64")
    return issues


def coerce_date_columns(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    """Convert date columns in place; report cells that are not valid dates."""
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for column in DATE_FIELDS:
        if column not in frame.columns:
            continue
        raw = frame[column]
        parsed = pd.to_datetime(raw, format=rules.date_format, errors="coerce")
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
                    message=(
                        f"{column} '{row[column]}' is not a valid date "
                        f"(expected format {rules.date_format})."
                    ),
                )
            )
        frame[column] = parsed
    return issues


# --- required fields ---------------------------------------------------------


def check_required_fields(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    columns = [column for column in rules.required_fields if column in frame.columns]
    for row in frame.to_dict("records"):
        for column in columns:
            if not is_missing(row[column]):
                continue
            if column == KEY_FIELD:
                message = "Required field employee_id is empty; the record cannot be matched across cycles."
            else:
                message = f"Required field {column} is empty."
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


def check_duplicates(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    issues: list[Issue] = []
    issues += _duplicate_keys(frame, dataset, rules)
    issues += _duplicate_values(
        frame,
        dataset,
        rules,
        column="email",
        normalize=lambda value: (normalize_text(value) or "").lower() or None,
        severity=rules.duplicates.email,
    )
    issues += _duplicate_values(
        frame,
        dataset,
        rules,
        column="iban",
        normalize=normalize_iban,
        severity=rules.duplicates.iban,
    )
    return issues


def _group_rows(
    frame: pd.DataFrame, column: str, normalize: Callable[[Any], str | None]
) -> dict[str, list[Row]]:
    """Rows sharing the same normalized value, only for values seen more than once."""
    if column not in frame.columns:
        return {}
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in frame.to_dict("records"):
        key = normalize(row.get(column))
        if key is not None:
            groups[key].append(row)
    return {key: rows for key, rows in groups.items() if len(rows) > 1}


def _duplicate_keys(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for key, rows in _group_rows(frame, KEY_FIELD, normalize_text).items():
        row_list = ", ".join(str(row[SOURCE_ROW]) for row in rows)
        issues.append(
            factory.issue(
                rows[0],
                category=Category.DUPLICATE,
                field=KEY_FIELD,
                rule="duplicate_employee_id",
                severity=rules.duplicates.employee_id,
                value=key,
                message=f"employee_id {key} appears {len(rows)} times (rows {row_list}).",
            )
        )
    return issues


def _duplicate_values(
    frame: pd.DataFrame,
    dataset: str,
    rules: Rules,
    *,
    column: str,
    normalize: Callable[[Any], str | None],
    severity: Severity,
) -> list[Issue]:
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    issues: list[Issue] = []
    for _, rows in _group_rows(frame, column, normalize).items():
        if len({_label(row) for row in rows}) < 2:
            continue  # the same record exported twice: already a duplicate-key issue
        for row in rows:
            others = sorted({_label(other) for other in rows if _label(other) != _label(row)})
            issues.append(
                factory.issue(
                    row,
                    category=Category.DUPLICATE,
                    field=column,
                    rule=f"duplicate_{column}",
                    severity=severity,
                    value=row[column],
                    message=f"{column} is shared with {', '.join(others)}.",
                )
            )
    return issues


def _label(row: Row) -> str:
    key = normalize_text(row.get(KEY_FIELD))
    return key if key else f"row {row[SOURCE_ROW]}"


# --- value ranges --------------------------------------------------------------


def check_value_ranges(frame: pd.DataFrame, dataset: str, rules: Rules) -> list[Issue]:
    """Values that parse fine but cannot be right."""
    factory = IssueFactory(dataset, rules)  # type: ignore[arg-type]
    severity = rules.invalid_values.severity
    issues: list[Issue] = []
    for row in frame.to_dict("records"):
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
                    message="monthly_salary is negative.",
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
                    message=f"end_date {end.date()} is earlier than start_date {start.date()}.",
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
                    message=f"email '{email}' does not look like a valid address.",
                )
            )
    return issues
