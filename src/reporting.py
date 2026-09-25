"""Turn a list of issues into a summary, a review queue and CSV exports."""

from __future__ import annotations

import io

import pandas as pd

from src.models import Category, Issue, ReconciliationResult, Severity, Summary

# Categories and lifecycle rules that describe a *difference* between the two cycles,
# as opposed to a problem within one dataset.
_CHANGE_CATEGORIES = {Category.SALARY_CHANGE, Category.IBAN_CHANGE, Category.CONTRACT_CHANGE}
_LIFECYCLE_CHANGE_RULES = {"start_date_changed", "end_date_added", "end_date_changed"}

EXPORT_COLUMNS = [
    "employee_id",
    "row_number",
    "dataset",
    "category",
    "field",
    "previous_value",
    "current_value",
    "change_percentage",
    "severity",
    "requires_review",
    "rule",
    "message",
]


def is_change(issue: Issue) -> bool:
    return issue.category in _CHANGE_CATEGORIES or issue.rule in _LIFECYCLE_CHANGE_RULES


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Most severe first, then grouped by category and record for a stable review order."""
    return sorted(
        issues,
        key=lambda issue: (
            -issue.severity.rank,
            issue.category.value,
            issue.employee_id or "",
            issue.row_number or 0,
            issue.field or "",
        ),
    )


def build_summary(issues: list[Issue], previous_records: int, current_records: int) -> Summary:
    by_severity = {severity: 0 for severity in Severity}
    for issue in issues:
        by_severity[issue.severity] += 1
    review_records = {
        issue.record_label for issue in issues if issue.requires_review
    }
    return Summary(
        previous_records=previous_records,
        current_records=current_records,
        new_records=sum(issue.rule == "new_record" for issue in issues),
        removed_records=sum(issue.rule == "removed_record" for issue in issues),
        critical_issues=by_severity[Severity.CRITICAL],
        warnings=by_severity[Severity.WARNING],
        info=by_severity[Severity.INFO],
        changes_detected=sum(is_change(issue) for issue in issues),
        records_requiring_review=len(review_records),
    )


def issues_to_frame(issues: list[Issue]) -> pd.DataFrame:
    """Flat table with one row per issue, enum values as plain strings."""
    records = [issue.model_dump(mode="json") for issue in issues]
    return pd.DataFrame.from_records(records, columns=EXPORT_COLUMNS)


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    """UTF-8 with BOM so the file opens cleanly in spreadsheet tools."""
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue().encode("utf-8-sig")


def full_report_csv(result: ReconciliationResult) -> bytes:
    return to_csv_bytes(issues_to_frame(result.issues))


def review_queue_csv(result: ReconciliationResult) -> bytes:
    return to_csv_bytes(issues_to_frame(result.review_queue))
