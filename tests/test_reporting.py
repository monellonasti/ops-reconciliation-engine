"""Summary counts and CSV exports."""

from __future__ import annotations

import io

import pandas as pd

from src.engine import run_reconciliation
from src.models import Category, Issue, Severity
from src.reporting import (
    EXPORT_COLUMNS,
    build_summary,
    full_report_csv,
    is_change,
    issues_to_frame,
    review_queue_csv,
    sort_issues,
)
from tests.conftest import employee


def issue(**overrides) -> Issue:
    base = dict(
        employee_id="EMP-00001",
        dataset="both",
        category=Category.SALARY_CHANGE,
        field="monthly_salary",
        rule="salary_change",
        severity=Severity.WARNING,
        requires_review=True,
        message="Monthly salary increased by 20.00%.",
    )
    base.update(overrides)
    return Issue(**base)


def test_summary_counts_by_severity_and_review_records():
    issues = [
        issue(severity=Severity.CRITICAL),
        issue(employee_id="EMP-00002", severity=Severity.WARNING),
        issue(employee_id="EMP-00002", category=Category.CONTRACT_CHANGE, rule="department_change",
              severity=Severity.INFO, requires_review=False),
        issue(employee_id="EMP-00003", category=Category.LIFECYCLE, rule="new_record",
              severity=Severity.INFO, requires_review=False),
        issue(employee_id="EMP-00004", category=Category.LIFECYCLE, rule="removed_record",
              severity=Severity.WARNING),
    ]

    summary = build_summary(issues, previous_records=10, current_records=11)

    assert summary.critical_issues == 1
    assert summary.warnings == 2
    assert summary.info == 2
    assert summary.total_issues == 5
    assert summary.new_records == 1
    assert summary.removed_records == 1
    assert summary.changes_detected == 3  # two salary changes and the department change
    assert summary.records_requiring_review == 3  # EMP-00001, EMP-00002, EMP-00004


def test_is_change_distinguishes_differences_from_data_problems():
    assert is_change(issue())
    assert is_change(issue(category=Category.LIFECYCLE, rule="end_date_added"))
    assert not is_change(issue(category=Category.LIFECYCLE, rule="new_record"))
    assert not is_change(issue(category=Category.MISSING_DATA, rule="missing_required_field"))
    assert not is_change(issue(category=Category.BONUS_ANOMALY, rule="bonus_ratio"))


def test_sort_issues_puts_critical_first_then_groups_by_category_and_record():
    issues = [
        issue(employee_id="EMP-00009", severity=Severity.INFO),
        issue(employee_id="EMP-00002", severity=Severity.CRITICAL, category=Category.IBAN_CHANGE),
        issue(employee_id="EMP-00001", severity=Severity.CRITICAL, category=Category.IBAN_CHANGE),
        issue(employee_id="EMP-00003", severity=Severity.WARNING),
    ]

    ordered = sort_issues(issues)

    assert [i.employee_id for i in ordered] == ["EMP-00001", "EMP-00002", "EMP-00003", "EMP-00009"]


def test_export_frame_has_the_documented_columns():
    frame = issues_to_frame([issue(change_percentage=20.0)])

    assert list(frame.columns) == EXPORT_COLUMNS
    assert frame.loc[0, "severity"] == "warning"
    assert frame.loc[0, "category"] == "salary_change"
    assert frame.loc[0, "change_percentage"] == 20.0


def test_exported_row_numbers_are_whole_numbers():
    """Row numbers point back to a line in the source file: 175, not 175.0."""
    from src.reporting import to_csv_bytes

    frame = issues_to_frame([issue(row_number=175, dataset="current"), issue(row_number=None)])
    lines = to_csv_bytes(frame).decode("utf-8-sig").splitlines()

    assert lines[1].split(",")[:2] == ["EMP-00001", "175"]
    assert lines[2].split(",")[:2] == ["EMP-00001", ""]


def test_export_frame_is_empty_but_well_formed_without_issues():
    frame = issues_to_frame([])

    assert list(frame.columns) == EXPORT_COLUMNS
    assert len(frame) == 0


def test_exports_are_utf8_with_bom_and_reviews_are_a_subset(make_loaded, rules):
    old_iban = "IT60X0542811101000000123456"
    result = run_reconciliation(
        make_loaded([employee(iban=old_iban, department="Sales")], "previous"),
        make_loaded([employee(iban="DE89370400440532013000", department="Finance")], "current"),
        rules,
    )

    full = full_report_csv(result)
    review = review_queue_csv(result)

    assert full.startswith("﻿".encode())
    full_frame = pd.read_csv(io.BytesIO(full))
    review_frame = pd.read_csv(io.BytesIO(review))
    assert len(full_frame) == 2
    assert len(review_frame) == 1
    assert review_frame.loc[0, "rule"] == "iban_change"
    assert old_iban not in full.decode("utf-8-sig")
    assert "IT60X****3456" in full.decode("utf-8-sig")
