"""Cross-cycle comparison: which records appeared, disappeared or changed.

Records are matched on ``employee_id``. Rows without a key cannot be matched
and are left to the validators to report. When a key appears more than once
the first row is used for comparison; the duplicate itself is reported by the
validators as a critical issue.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.config import RuleOutcome, Rules
from src.models import KEY_FIELD, NUMERIC_FIELDS, Category, Issue, Severity
from src.utils import (
    display_value,
    format_value,
    is_missing,
    mask_iban,
    normalize_iban,
    normalize_text,
    percentage_change,
)
from src.validators import ValidatedDataset


def reconcile(previous: ValidatedDataset, current: ValidatedDataset, rules: Rules) -> list[Issue]:
    """Compare two validated cycles and return every lifecycle and field-change issue."""
    before = index_by_key(previous.frame)
    after = index_by_key(current.frame)

    issues: list[Issue] = []
    issues += detect_new_records(before, after, rules)
    issues += detect_removed_records(before, after, rules)
    for key in before.index.intersection(after.index).sort_values():
        issues += compare_record(key, before.loc[key], after.loc[key], rules)
    return issues


def index_by_key(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per key: rows without a key are dropped, repeated keys keep the first row."""
    keys = frame[KEY_FIELD].map(normalize_text)
    keyed = frame.loc[keys.notna()].copy()
    keyed[KEY_FIELD] = keys[keys.notna()]
    keyed = keyed.drop_duplicates(subset=KEY_FIELD, keep="first")
    return keyed.set_index(KEY_FIELD)


# --- lifecycle -----------------------------------------------------------------


def detect_new_records(before: pd.DataFrame, after: pd.DataFrame, rules: Rules) -> list[Issue]:
    outcome = rules.lifecycle.new_record
    return [
        _lifecycle_issue(
            key,
            dataset="current",
            rule="new_record",
            outcome=outcome,
            rules=rules,
            message=f"New record{_name_suffix(after.loc[key])}: not present in the previous cycle.",
        )
        for key in after.index.difference(before.index)
    ]


def detect_removed_records(before: pd.DataFrame, after: pd.DataFrame, rules: Rules) -> list[Issue]:
    outcome = rules.lifecycle.removed_record
    return [
        _lifecycle_issue(
            key,
            dataset="previous",
            rule="removed_record",
            outcome=outcome,
            rules=rules,
            message=f"Record removed{_name_suffix(before.loc[key])}: present in the previous cycle only.",
        )
        for key in before.index.difference(after.index)
    ]


def _name_suffix(row: pd.Series) -> str:
    name = " ".join(
        part for part in (normalize_text(row.get("first_name")), normalize_text(row.get("last_name"))) if part
    )
    return f" ({name})" if name else ""


def _lifecycle_issue(
    key: str, *, dataset: str, rule: str, outcome: RuleOutcome, rules: Rules, message: str
) -> Issue:
    return Issue(
        employee_id=key,
        dataset=dataset,  # type: ignore[arg-type]
        category=Category.LIFECYCLE,
        field=None,
        rule=rule,
        severity=outcome.severity,
        requires_review=rules.outcome_requires_review(outcome),
        message=message,
    )


# --- matched records -----------------------------------------------------------


def compare_record(key: str, before: pd.Series, after: pd.Series, rules: Rules) -> list[Issue]:
    """All field-level differences between the two versions of one record."""
    issues: list[Issue] = []
    issues += compare_salary(key, before, after, rules)
    issues += compare_iban(key, before, after, rules)
    contract_fields = (
        ("contract_type", rules.contract_changes.contract_type),
        ("working_hours", rules.contract_changes.working_hours),
        ("department", rules.contract_changes.department),
    )
    for field, outcome in contract_fields:
        issues += compare_field(key, before, after, field, outcome, rules)
    issues += compare_dates(key, before, after, rules)
    return issues


def salary_change_severity(change_percentage: float, rules: Rules) -> Severity:
    """Map an absolute percentage change onto the configured thresholds."""
    magnitude = abs(change_percentage)
    if magnitude > rules.salary_change.critical_percentage:
        return Severity.CRITICAL
    if magnitude > rules.salary_change.warning_percentage:
        return Severity.WARNING
    return Severity.INFO


def compare_salary(key: str, before: pd.Series, after: pd.Series, rules: Rules) -> list[Issue]:
    field = "monthly_salary"
    prev, curr = before.get(field), after.get(field)
    if is_missing(curr) or _same(prev, curr):
        return []  # a missing current salary is already a missing-data issue

    if is_missing(prev):
        return [
            _change_issue(
                key, field, prev, curr, rules,
                category=Category.SALARY_CHANGE, rule="salary_change", severity=Severity.INFO,
                message=f"Monthly salary set to {format_value(curr)}; no previous value to compare.",
            )
        ]

    change = percentage_change(prev, curr)
    if change is None:  # previous salary was zero
        return [
            _change_issue(
                key, field, prev, curr, rules,
                category=Category.SALARY_CHANGE, rule="salary_change", severity=Severity.WARNING,
                message=f"Monthly salary changed from 0 to {format_value(curr)}; percentage not meaningful.",
            )
        ]

    direction = "increased" if change > 0 else "decreased"
    return [
        _change_issue(
            key, field, prev, curr, rules,
            category=Category.SALARY_CHANGE, rule="salary_change",
            severity=salary_change_severity(change, rules), change_percentage=change,
            message=(
                f"Monthly salary {direction} by {abs(change):.2f}% "
                f"(from {format_value(prev)} to {format_value(curr)})."
            ),
        )
    ]


def compare_iban(key: str, before: pd.Series, after: pd.Series, rules: Rules) -> list[Issue]:
    prev, curr = before.get("iban"), after.get("iban")
    prev_norm, curr_norm = normalize_iban(prev), normalize_iban(curr)
    if prev_norm == curr_norm:
        return []

    if prev_norm is None:
        message = f"IBAN added ({mask_iban(curr)}); no IBAN in the previous cycle."
    elif curr_norm is None:
        message = f"IBAN removed (was {mask_iban(prev)})."
    else:
        message = f"IBAN changed from {mask_iban(prev)} to {mask_iban(curr)}."

    return [
        _change_issue(
            key, "iban", prev, curr, rules,
            category=Category.IBAN_CHANGE, rule="iban_change",
            severity=rules.iban_change.severity,
            requires_review=rules.iban_change.requires_review,
            message=message,
        )
    ]


def compare_field(
    key: str, before: pd.Series, after: pd.Series, field: str, outcome: RuleOutcome, rules: Rules
) -> list[Issue]:
    """Generic change detection for one column, with the outcome taken from the rules."""
    prev, curr = before.get(field), after.get(field)
    if _same(prev, curr):
        return []
    change = percentage_change(prev, curr) if field in NUMERIC_FIELDS else None
    return [
        _change_issue(
            key, field, prev, curr, rules,
            category=Category.CONTRACT_CHANGE, rule=f"{field}_change",
            severity=outcome.severity, requires_review=outcome.requires_review,
            change_percentage=change,
            message=f"{field} changed from {_shown(prev)} to {_shown(curr)}.",
        )
    ]


def compare_dates(key: str, before: pd.Series, after: pd.Series, rules: Rules) -> list[Issue]:
    issues: list[Issue] = []
    lifecycle = rules.lifecycle

    prev_start, curr_start = before.get("start_date"), after.get("start_date")
    if not _same(prev_start, curr_start):
        issues.append(
            _change_issue(
                key, "start_date", prev_start, curr_start, rules,
                category=Category.LIFECYCLE, rule="start_date_changed",
                severity=lifecycle.start_date_changed.severity,
                requires_review=lifecycle.start_date_changed.requires_review,
                message=f"start_date changed from {_shown(prev_start)} to {_shown(curr_start)}.",
            )
        )

    prev_end, curr_end = before.get("end_date"), after.get("end_date")
    if is_missing(prev_end) and not is_missing(curr_end):
        issues.append(
            _change_issue(
                key, "end_date", prev_end, curr_end, rules,
                category=Category.LIFECYCLE, rule="end_date_added",
                severity=lifecycle.end_date_added.severity,
                requires_review=lifecycle.end_date_added.requires_review,
                message=f"end_date added: {format_value(curr_end)}.",
            )
        )
    elif not _same(prev_end, curr_end):
        issues.append(
            _change_issue(
                key, "end_date", prev_end, curr_end, rules,
                category=Category.LIFECYCLE, rule="end_date_changed",
                severity=lifecycle.end_date_changed.severity,
                requires_review=lifecycle.end_date_changed.requires_review,
                message=f"end_date changed from {_shown(prev_end)} to {_shown(curr_end)}.",
            )
        )
    return issues


# --- helpers ---------------------------------------------------------------------


def _same(prev: Any, curr: Any) -> bool:
    """Equality that treats all missing values as equal and ignores case/whitespace in text."""
    if is_missing(prev) and is_missing(curr):
        return True
    if is_missing(prev) or is_missing(curr):
        return False
    if isinstance(prev, str) or isinstance(curr, str):
        return str(prev).strip().lower() == str(curr).strip().lower()
    return bool(prev == curr)


def _shown(value: Any) -> str:
    return format_value(value) or "empty"


def _change_issue(
    key: str,
    field: str,
    prev: Any,
    curr: Any,
    rules: Rules,
    *,
    category: Category,
    rule: str,
    severity: Severity,
    message: str,
    requires_review: bool | None = None,
    change_percentage: float | None = None,
) -> Issue:
    return Issue(
        employee_id=key,
        dataset="both",
        category=category,
        field=field,
        previous_value=display_value(field, prev, rules.masked_fields),
        current_value=display_value(field, curr, rules.masked_fields),
        change_percentage=change_percentage,
        rule=rule,
        severity=severity,
        requires_review=rules.requires_review(severity, requires_review),
        message=message,
    )
