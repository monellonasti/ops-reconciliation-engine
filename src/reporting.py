"""Turn a list of issues into a summary, a review queue and CSV exports."""

from __future__ import annotations

import io

import pandas as pd

from src.models import Category, Issue, ReconciliationResult, ReviewStatus, Severity, Summary

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
    "review_status",
    "review_note",
    "reviewed_by",
    "reviewed_at",
    "expected_reference",
    "expected_mismatch",
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
        ("key", issue.employee_id) if issue.employee_id else (issue.dataset, issue.row_number)
        for issue in issues
        if issue.requires_review and issue.review_status is not ReviewStatus.ACCEPTED
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
        accepted_findings=sum(i.review_status is ReviewStatus.ACCEPTED for i in issues),
        needs_action_findings=sum(i.review_status is ReviewStatus.NEEDS_ACTION for i in issues),
        expected_matched=sum(i.expected_reference is not None for i in issues),
        expected_mismatched=sum(
            i.expected_mismatch is not None and i.rule != "expected_change_missing" for i in issues
        ),
        expected_missing=sum(i.rule == "expected_change_missing" for i in issues),
    )


def issues_to_frame(issues: list[Issue]) -> pd.DataFrame:
    """Flat table with one row per issue, enum values as plain strings."""
    records = [issue.model_dump(mode="json") for issue in issues]
    return pd.DataFrame.from_records(records, columns=EXPORT_COLUMNS)


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    """UTF-8 with BOM so the file opens cleanly in spreadsheet tools."""
    buffer = io.StringIO()
    safe = frame.map(
        lambda value: "'" + value
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
        else value
    )
    safe.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue().encode("utf-8-sig")


def full_report_csv(result: ReconciliationResult) -> bytes:
    return to_csv_bytes(issues_to_frame(result.issues))


def review_queue_csv(result: ReconciliationResult) -> bytes:
    return to_csv_bytes(issues_to_frame(result.review_queue))
