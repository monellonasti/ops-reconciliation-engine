"""Expected changes: approvals known before the run, supplied as an optional CSV.

The file has the columns ``employee_id``, ``field``, ``expected_value`` and an
optional ``reference`` (ticket, approver, date). ``field`` is one of the
comparable columns (monthly_salary, iban, contract_type, working_hours,
department, start_date, end_date) or one of the lifecycle events
``new_record`` / ``removed_record``, for which ``expected_value`` stays blank.

What it does to the findings of a run:

- a change that matches an expectation (same record, same field, same new
  value) is downgraded to INFO and marked with the reference; IBAN changes
  keep their severity and are only marked, because they are always reviewed;
- a change to a *different* value than expected keeps its severity and says
  what was expected instead;
- an expectation that did not happen becomes a finding of its own.

The file is an operator input processed in memory like the two cycles; the
values it contains never enter a finding unmasked.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel

from src.config import Rules
from src.loader import DatasetLoadError, Source, read_table
from src.models import DATE_FIELDS, KEY_FIELD, NUMERIC_FIELDS, SOURCE_ROW, Category, Issue, Severity
from src.utils import display_value, format_value, is_missing, normalize_iban, normalize_text

COMPARABLE_FIELDS = (
    "monthly_salary",
    "iban",
    "contract_type",
    "working_hours",
    "department",
    "start_date",
    "end_date",
)
LIFECYCLE_EVENTS = ("new_record", "removed_record")
EXPECTABLE_FIELDS = COMPARABLE_FIELDS + LIFECYCLE_EVENTS

# Which change rules describe each expectable field.
_RULES_BY_FIELD: dict[str, set[str]] = {
    "monthly_salary": {"salary_change"},
    "iban": {"iban_change"},
    "contract_type": {"contract_type_change"},
    "working_hours": {"working_hours_change"},
    "department": {"department_change"},
    "start_date": {"start_date_changed"},
    "end_date": {"end_date_added", "end_date_changed"},
    "new_record": {"new_record"},
    "removed_record": {"removed_record"},
}
# Product invariant: an expected IBAN change is still reviewed by a person.
_NEVER_DOWNGRADED = {"iban_change"}

Records = dict[str, dict[str, Any]]


class ExpectedChange(BaseModel):
    employee_id: str
    field: str
    expected_value: str | None = None
    reference: str | None = None
    row_number: int

    @property
    def label(self) -> str:
        return self.reference or f"expected changes row {self.row_number}"


class ExpectedChanges:
    """The expectations of one run and which of them were met."""

    def __init__(self, changes: list[ExpectedChange]):
        self._by_key: dict[tuple[str, str], ExpectedChange] = {
            (change.employee_id, change.field): change for change in changes
        }
        self._consumed: set[tuple[str, str]] = set()

    def __len__(self) -> int:
        return len(self._by_key)

    def lookup(self, employee_id: str | None, field: str) -> ExpectedChange | None:
        return self._by_key.get((employee_id or "", field))

    def apply(self, issue: Issue, actual: Any, rules: Rules) -> Issue:
        """Adjust one change finding for a matching expectation (and remember it was used)."""
        field = issue.rule if issue.rule in LIFECYCLE_EVENTS else issue.field
        if field is None or issue.rule not in _RULES_BY_FIELD.get(field, set()):
            return issue
        change = self.lookup(issue.employee_id, field)
        if change is None:
            return issue
        self._consumed.add((change.employee_id, change.field))

        if field in LIFECYCLE_EVENTS or values_equal(field, change.expected_value, actual, rules):
            note = f"Matches expected change ({change.label})."
            if issue.rule in _NEVER_DOWNGRADED:
                note += " IBAN changes are always reviewed."
                return issue.model_copy(
                    update={"message": f"{issue.message} {note}", "expected_reference": change.label}
                )
            return issue.model_copy(
                update={
                    "severity": Severity.INFO,
                    "requires_review": rules.requires_review(Severity.INFO),
                    "message": f"{issue.message} {note}",
                    "expected_reference": change.label,
                }
            )

        shown = _shown_expected(field, change.expected_value, rules)
        return issue.model_copy(
            update={
                "message": f"{issue.message} Differs from the expected value {shown} ({change.label}).",
                "expected_mismatch": str(shown),
            }
        )

    def unmet(self) -> list[ExpectedChange]:
        return [change for key, change in self._by_key.items() if key not in self._consumed]

    def missing_issues(self, before: Records, after: Records, rules: Rules) -> list[Issue]:
        """One finding per expectation that did not happen."""
        severity = rules.expected_changes.missing_severity
        issues = []
        for change in self.unmet():
            key = change.employee_id
            in_before, in_after = key in before, key in after
            current = after[key].get(change.field) if in_after and change.field in COMPARABLE_FIELDS else None
            if current is not None and values_equal(change.field, change.expected_value, current, rules):
                continue  # already in place before this cycle: nothing changed, nothing is missing
            issues.append(
                Issue(
                    employee_id=key,
                    row_number=change.row_number,
                    dataset="current",
                    category=Category.EXPECTED_CHANGE,
                    field=change.field if change.field in COMPARABLE_FIELDS else None,
                    current_value=display_value(change.field, current, rules.masked_fields),
                    rule="expected_change_missing",
                    severity=severity,
                    requires_review=rules.requires_review(severity),
                    message=_missing_message(change, in_before, in_after, current, rules),
                    expected_mismatch=str(_shown_expected(change.field, change.expected_value, rules))
                    if change.field in COMPARABLE_FIELDS
                    else None,
                )
            )
        return issues


# --- loading -------------------------------------------------------------------------


def load_expected_changes(source: Source) -> ExpectedChanges:
    """Read the expected changes CSV. Every row must be usable: this file is small,
    hand-made and represents approvals, so problems are errors rather than skips."""
    table = read_table(source)
    required = ("employee_id", "field", "expected_value")
    missing = [column for column in required if column not in table.header]
    if missing:
        raise DatasetLoadError(
            f"Expected changes file: missing column(s) {', '.join(missing)}. "
            f"Required: {', '.join(required)}; optional: reference."
        )
    if table.skipped:
        lines = ", ".join(str(line) for line, _ in table.skipped)
        raise DatasetLoadError(f"Expected changes file: row(s) {lines} have the wrong number of fields.")

    changes: list[ExpectedChange] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for record in table.records():
        line = record[SOURCE_ROW]
        employee_id = normalize_text(record.get(KEY_FIELD))
        field = (normalize_text(record.get("field")) or "").lower()
        value = normalize_text(record.get("expected_value"))
        if not employee_id:
            problems.append(f"row {line}: employee_id is empty")
        elif field not in EXPECTABLE_FIELDS:
            problems.append(f"row {line}: field '{field}' is not one of {', '.join(EXPECTABLE_FIELDS)}")
        elif field in COMPARABLE_FIELDS and value is None:
            problems.append(f"row {line}: expected_value is required for {field}")
        elif field in LIFECYCLE_EVENTS and value is not None:
            problems.append(f"row {line}: expected_value must be empty for {field}")
        elif (employee_id, field) in seen:
            problems.append(f"row {line}: {employee_id} / {field} is listed more than once")
        else:
            seen.add((employee_id, field))
            changes.append(
                ExpectedChange(
                    employee_id=employee_id,
                    field=field,
                    expected_value=value,
                    reference=normalize_text(record.get("reference")),
                    row_number=line,
                )
            )
    if problems:
        shown = "; ".join(problems[:5]) + (f"; and {len(problems) - 5} more" if len(problems) > 5 else "")
        raise DatasetLoadError(f"Expected changes file: {shown}.")
    return ExpectedChanges(changes)


# --- helpers -------------------------------------------------------------------------


def values_equal(field: str, expected: str | None, actual: Any, rules: Rules) -> bool:
    """Compare an expected value written in the CSV with the typed value of the current cycle."""
    if expected is None or is_missing(actual):
        return expected is None and is_missing(actual)
    if field in NUMERIC_FIELDS:
        try:
            return float(expected) == float(actual)
        except (TypeError, ValueError):
            return False
    if field in DATE_FIELDS:
        parsed = pd.to_datetime(expected, format=rules.date_format, errors="coerce")
        return not pd.isna(parsed) and pd.Timestamp(actual).normalize() == parsed.normalize()
    if field == "iban":
        return normalize_iban(expected) == normalize_iban(actual)
    return (normalize_text(expected) or "").lower() == (normalize_text(actual) or "").lower()


def _shown_expected(field: str, expected: str | None, rules: Rules) -> str | float | None:
    """Expected value as it may appear in a finding: masked like any other value."""
    if expected is None:
        return None
    if field in NUMERIC_FIELDS:
        try:
            return format_value(float(expected))
        except ValueError:
            return expected
    return display_value(field, expected, rules.masked_fields)


def _missing_message(
    change: ExpectedChange, in_before: bool, in_after: bool, current: Any, rules: Rules
) -> str:
    key = change.employee_id
    if change.field == "new_record":
        if in_after and in_before:
            return f"Expected {key} as a new record ({change.label}) but it already existed in the previous cycle."
        return f"Expected {key} as a new record ({change.label}) but it is not present in the current cycle."
    if change.field == "removed_record":
        if in_after:
            return f"Expected {key} to be removed ({change.label}) but it is still present in the current cycle."
        return f"Expected {key} to be removed ({change.label}) but it was not present in the previous cycle either."

    expected = _shown_expected(change.field, change.expected_value, rules)
    head = f"Expected {change.field} to become {expected} ({change.label})"
    if not in_after and not in_before:
        return f"{head} but the record is not present in either cycle."
    if not in_after:
        return f"{head} but the record is absent from the current cycle."
    shown = display_value(change.field, current, rules.masked_fields)
    return f"{head} but the current value is {format_value(shown) or 'empty'}."
