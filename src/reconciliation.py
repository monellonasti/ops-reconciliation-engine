"""Cross-cycle comparison: which records appeared, disappeared or changed.

Records are matched on ``employee_id``. Rows without a key cannot be matched
and are left to the validators to report. When a key appears more than once
that key is excluded from comparison in both cycles; validators report a critical
issue requiring human review.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.config import RuleOutcome, Rules
from src.expectations import ExpectedChanges
from src.models import KEY_FIELD, NUMERIC_FIELDS, Category, Issue, Severity
from src.utils import (
    display_value,
    format_value,
    is_missing,
    mask_iban,
    normalize_iban,
    normalize_text,
    format_change,
    percentage_change,
    redact_message,
)
from src.validators import ValidatedDataset

Row = dict[str, Any]
Records = dict[str, Row]


def reconcile(
    previous: ValidatedDataset,
    current: ValidatedDataset,
    rules: Rules,
    expected: ExpectedChanges | None = None,
) -> list[Issue]:
    """Compare two validated cycles and return every lifecycle and field-change issue.

    With ``expected``, findings that match an approved change are downgraded and
    approved changes that did not happen are reported.
    """
    before = index_by_key(previous.frame)
    after = index_by_key(current.frame)
    ambiguous = set()
    for dataset in (previous, current):
        keys = dataset.frame[KEY_FIELD].map(normalize_text)
        ambiguous.update(keys[keys.notna() & keys.duplicated(keep=False)])
    for key in ambiguous:
        before.pop(key, None)
        after.pop(key, None)

    unavailable = previous.missing_columns | current.missing_columns
    for record in list(before.values()) + list(after.values()):
        for field in unavailable:
            record[field] = None

    issues: list[Issue] = []
    issues += detect_new_records(before, after, rules)
    issues += detect_removed_records(before, after, rules)
    for key in sorted(before.keys() & after.keys()):
        issues += compare_record(key, before[key], after[key], rules)
    if expected is not None:
        issues = [expected.apply(issue, _current_value(issue, after), rules) for issue in issues]
        issues += expected.missing_issues(before, after, rules)
    return issues


def _current_value(issue: Issue, after: Records) -> Any:
    """Raw current-cycle value behind a change finding, for comparison with an expectation."""
    if issue.employee_id in after and issue.field:
        return after[issue.employee_id].get(issue.field)
    return None


def index_by_key(frame: pd.DataFrame) -> Records:
    """One row per key: rows without a key are dropped, repeated keys keep the first row."""
    keys = frame[KEY_FIELD].map(normalize_text)
    keyed = frame.loc[keys.notna()].copy()
    keyed[KEY_FIELD] = keys[keys.notna()]
    keyed = keyed.drop_duplicates(subset=KEY_FIELD, keep="first")
    return keyed.set_index(KEY_FIELD).to_dict("index")


# --- lifecycle -----------------------------------------------------------------


def detect_new_records(before: Records, after: Records, rules: Rules) -> list[Issue]:
    outcome = rules.lifecycle.new_record
    return [
        _lifecycle_issue(
            key,
            dataset="current",
            rule="new_record",
            outcome=outcome,
            rules=rules,
            message=f"New record{_name_suffix(after[key], rules)}: not present in the previous cycle.",
        )
        for key in sorted(after.keys() - before.keys())
    ]


def detect_removed_records(before: Records, after: Records, rules: Rules) -> list[Issue]:
    outcome = rules.lifecycle.removed_record
    return [
        _lifecycle_issue(
            key,
            dataset="previous",
            rule="removed_record",
            outcome=outcome,
            rules=rules,
            message=(
                f"Record removed{_name_suffix(before[key], rules)}: present in the previous cycle only."
            ),
        )
        for key in sorted(before.keys() - after.keys())
    ]


def _name_suffix(row: Row, rules: Rules) -> str:
    parts = tuple(display_value(field, row.get(field), rules.masked_fields)
                  for field in ("first_name", "last_name"))
    name = " ".join(part for part in parts if part)
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


def compare_record(key: str, before: Row, after: Row, rules: Rules) -> list[Issue]:
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


def compare_salary(key: str, before: Row, after: Row, rules: Rules) -> list[Issue]:
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

    change = percentage_change(prev, curr, rounded=False)
    if change is None:  # previous salary was zero
        return [
            _change_issue(
                key, field, prev, curr, rules,
                category=Category.SALARY_CHANGE, rule="salary_change", severity=Severity.WARNING,
                message=(
                    f"Monthly salary changed from 0 to {format_value(curr)}; "
                    "percentage not meaningful."
                ),
            )
        ]

    direction = "increased" if change > 0 else "decreased"
    thresholds = (rules.salary_change.warning_percentage, rules.salary_change.critical_percentage)
    return [
        _change_issue(
            key, field, prev, curr, rules,
            category=Category.SALARY_CHANGE, rule="salary_change",
            severity=salary_change_severity(change, rules), change_percentage=round(change, 6),
            message=(
                f"Monthly salary {direction} by {format_change(change, thresholds)}% "
                f"(from {format_value(prev)} to {format_value(curr)})."
            ),
        )
    ]


def compare_iban(key: str, before: Row, after: Row, rules: Rules) -> list[Issue]:
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
    key: str, before: Row, after: Row, field: str, outcome: RuleOutcome, rules: Rules
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


def compare_dates(key: str, before: Row, after: Row, rules: Rules) -> list[Issue]:
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
        message=redact_message(message, [{field: prev}, {field: curr}], rules.masked_fields),
    )
