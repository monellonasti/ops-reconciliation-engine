"""Expected changes: approvals known before the run, supplied as an optional CSV or Excel file.

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
from src.i18n import t
from src.loader import DatasetLoadError, Source, read_table
from src.models import DATE_FIELDS, KEY_FIELD, NUMERIC_FIELDS, SOURCE_ROW, Category, Issue, Severity
from src.utils import (
    display_value,
    format_value,
    is_missing,
    normalize_iban,
    normalize_text,
    parse_number,
)

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
        return self.reference or t("expected.row_label", line=self.row_number)


class ExpectedChanges:
    """The expectations of one run and which of them were met."""

    def __init__(self, changes: list[ExpectedChange]):
        self._by_key: dict[tuple[str, str], ExpectedChange] = {
            (change.employee_id, change.field): change for change in changes
        }
        self._consumed: set[tuple[str, str]] = set()

    def __len__(self) -> int:
        return len(self._by_key)

    def reset(self) -> None:
        """Forget which expectations were met, before a new run reuses this object."""
        self._consumed.clear()

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
            note = t("expected.matches", reference=change.label)
            if issue.rule in _NEVER_DOWNGRADED:
                note = f"{note} {t('expected.iban_reviewed')}"
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
                "message": f"{issue.message} {t('expected.differs', expected=shown, reference=change.label)}",
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
    """Read the expected changes file. Every row must be usable: this file is small,
    hand-made and represents approvals, so problems are errors rather than skips."""
    table = read_table(source)
    required = ("employee_id", "field", "expected_value")
    missing = [column for column in required if column not in table.header]
    if missing:
        raise DatasetLoadError(
            t("expected.load.missing_columns", missing=", ".join(missing), required=", ".join(required))
        )
    if table.skipped:
        lines = ", ".join(str(line) for line, _ in table.skipped)
        raise DatasetLoadError(t("expected.load.bad_rows", lines=lines))

    changes: list[ExpectedChange] = []
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for record in table.records():
        line = record[SOURCE_ROW]
        employee_id = normalize_text(record.get(KEY_FIELD))
        field = (normalize_text(record.get("field")) or "").lower()
        value = _expected_text(record.get("expected_value"))
        if not employee_id:
            problems.append(t("expected.load.empty_id", line=line))
        elif field not in EXPECTABLE_FIELDS:
            problems.append(
                t("expected.load.bad_field", line=line, field=field, allowed=", ".join(EXPECTABLE_FIELDS))
            )
        elif field in COMPARABLE_FIELDS and value is None:
            problems.append(t("expected.load.value_required", line=line, field=field))
        elif field in LIFECYCLE_EVENTS and value is not None:
            problems.append(t("expected.load.value_forbidden", line=line, field=field))
        elif (employee_id, field) in seen:
            problems.append(t("expected.load.duplicate", line=line, key=employee_id, field=field))
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
        shown = "; ".join(problems[:5])
        if len(problems) > 5:
            shown += t("expected.load.more", count=len(problems) - 5)
        raise DatasetLoadError(t("expected.load.problems", problems=shown))
    return ExpectedChanges(changes)


def _expected_text(value: Any) -> str | None:
    """Excel gives numbers and dates as objects; keep a canonical text form for them."""
    if is_missing(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return str(int(number)) if number.is_integer() else repr(number)
    if hasattr(value, "date"):
        return value.date().isoformat() if hasattr(value.date(), "isoformat") else str(value)
    return normalize_text(value)


# --- helpers -------------------------------------------------------------------------


def values_equal(field: str, expected: str | None, actual: Any, rules: Rules) -> bool:
    """Compare an expected value written in the file with the typed value of the current cycle."""
    if expected is None or is_missing(actual):
        return expected is None and is_missing(actual)
    if field in NUMERIC_FIELDS:
        number = parse_number(expected)
        if number is None:
            # Excel or ISO-style text ("2400.5") is accepted regardless of the input convention.
            try:
                number = float(expected)
            except ValueError:
                return False
        return number == float(actual)
    if field in DATE_FIELDS:
        parsed = _parse_expected_date(expected, rules)
        return parsed is not None and pd.Timestamp(actual).normalize() == parsed.normalize()
    if field == "iban":
        return normalize_iban(expected) == normalize_iban(actual)
    return (normalize_text(expected) or "").lower() == (normalize_text(actual) or "").lower()


def _parse_expected_date(text: str, rules: Rules) -> pd.Timestamp | None:
    for pattern in [*rules.formats.input_date_formats, "%Y-%m-%d"]:
        parsed = pd.to_datetime(text, format=pattern, errors="coerce")
        if not pd.isna(parsed):
            return parsed
    return None


def _shown_expected(field: str, expected: str | None, rules: Rules) -> str | float | None:
    """Expected value as it may appear in a finding: masked like any other value."""
    if expected is None:
        return None
    if field in NUMERIC_FIELDS:
        number = parse_number(expected)
        if number is None:
            try:
                number = float(expected)
            except ValueError:
                return expected
        return format_value(number)
    if field in DATE_FIELDS:
        parsed = _parse_expected_date(expected, rules)
        return format_value(parsed) if parsed is not None else expected
    return display_value(field, expected, rules.masked_fields)


def _missing_message(
    change: ExpectedChange, in_before: bool, in_after: bool, current: Any, rules: Rules
) -> str:
    key = change.employee_id
    if change.field == "new_record":
        if in_after and in_before:
            return t("expected.missing.new_existed", key=key, reference=change.label)
        return t("expected.missing.new_absent", key=key, reference=change.label)
    if change.field == "removed_record":
        if in_after:
            return t("expected.missing.removed_present", key=key, reference=change.label)
        return t("expected.missing.removed_absent", key=key, reference=change.label)

    expected = _shown_expected(change.field, change.expected_value, rules)
    head = t("expected.missing.head", field=change.field, expected=expected, reference=change.label)
    if not in_after and not in_before:
        return t("expected.missing.neither", head=head)
    if not in_after:
        return t("expected.missing.absent", head=head)
    shown = display_value(change.field, current, rules.masked_fields)
    return t("expected.missing.current", head=head, current=format_value(shown) or t("value.empty"))
