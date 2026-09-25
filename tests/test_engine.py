"""End-to-end runs through the orchestrator, including configurable thresholds and the CLI."""

from __future__ import annotations

from src.config import rules_from_dict
from src.engine import main, reconcile_sources, run_reconciliation
from src.models import Severity
from tests.conftest import csv_bytes, employee


def previous_rows():
    return [
        employee(),
        employee(employee_id="EMP-00002", first_name="Bea", email="bea@example.com",
                 iban="IT00X0000000000000000000002", contract_type="part_time",
                 department="Sales", working_hours="20", monthly_salary="1500"),
        employee(employee_id="EMP-00003", first_name="Cy", email="cy@example.com",
                 iban="IT00X0000000000000000000003", monthly_salary="3000", bonus="100"),
    ]


def current_rows():
    return [
        employee(iban="IT60X0542811101000000999999", monthly_salary="3000"),
        employee(employee_id="EMP-00002", first_name="Bea", email="bea@example.com",
                 iban="IT00X0000000000000000000002", contract_type="full_time",
                 department="Finance", working_hours="40", monthly_salary="1500",
                 bonus="2000", overtime_hours="75", end_date="2024-12-31"),
        employee(employee_id="EMP-00004", first_name="Dee", email="dee@example.com",
                 iban="IT00X0000000000000000000004", monthly_salary="2500",
                 overtime_hours="-3", start_date="2024-02-30"),
    ]


def test_end_to_end_summary(make_loaded, rules):
    result = run_reconciliation(
        make_loaded(previous_rows(), "previous"), make_loaded(current_rows(), "current"), rules
    )

    summary = result.summary
    assert summary.previous_records == 3
    assert summary.current_records == 3
    assert summary.new_records == 1
    assert summary.removed_records == 1
    assert summary.critical_issues == 5  # bonus, iban, invalid date, negative overtime, salary
    assert summary.warnings == 5  # contract, hours, end date, removed, overtime
    assert summary.info == 2  # department change, new record
    assert summary.changes_detected == 6
    assert summary.records_requiring_review == 4
    assert {issue.rule for issue in result.issues} == {
        "bonus_ratio", "iban_change", "invalid_date", "overtime_hours", "salary_change",
        "contract_type_change", "working_hours_change", "end_date_added", "removed_record",
        "department_change", "new_record",
    }


def test_issues_are_sorted_most_severe_first(make_loaded, rules):
    result = run_reconciliation(
        make_loaded(previous_rows(), "previous"), make_loaded(current_rows(), "current"), rules
    )

    ranks = [issue.severity.rank for issue in result.issues]
    assert ranks == sorted(ranks, reverse=True)


def test_review_queue_contains_only_flagged_issues(make_loaded, rules):
    result = run_reconciliation(
        make_loaded(previous_rows(), "previous"), make_loaded(current_rows(), "current"), rules
    )

    assert result.review_queue
    assert all(issue.requires_review for issue in result.review_queue)
    assert all(issue.severity is not Severity.INFO for issue in result.review_queue)


def test_loader_issues_and_notes_are_carried_through(rules):
    current = (
        b"employee_id,first_name,last_name,contract_type,monthly_salary\n"
        b"EMP-00001,Ada,Rossi,full_time,2100\n"
        b"EMP-00002,Bea,Bianchi,full_time,2100,EXTRA\n"
    )

    result = reconcile_sources(csv_bytes([employee()]), current, rules)

    assert any(issue.rule == "malformed_row" for issue in result.issues)
    assert any("Optional column" in note for note in result.notes)


def test_thresholds_come_from_the_rules_not_the_code(make_loaded):
    lenient = rules_from_dict({"salary_change": {"warning_percentage": 50, "critical_percentage": 100}})
    strict = rules_from_dict({"salary_change": {"warning_percentage": 5, "critical_percentage": 10}})
    previous = [employee(monthly_salary="2100")]
    current = [employee(monthly_salary="3000")]  # +42.86%

    lenient_issue = run_reconciliation(
        make_loaded(previous, "previous"), make_loaded(current, "current"), lenient
    ).issues[0]
    strict_issue = run_reconciliation(
        make_loaded(previous, "previous"), make_loaded(current, "current"), strict
    ).issues[0]

    assert lenient_issue.severity is Severity.INFO
    assert lenient_issue.requires_review is False
    assert strict_issue.severity is Severity.CRITICAL


def test_review_policy_is_configurable(make_loaded):
    review_everything = rules_from_dict({"review_policy": {"info": True, "warning": True, "critical": True}})

    result = run_reconciliation(
        make_loaded([employee(department="Sales")], "previous"),
        make_loaded([employee(department="Finance")], "current"),
        review_everything,
    )

    assert result.issues[0].severity is Severity.INFO
    assert result.issues[0].requires_review is True


def test_cli_writes_both_reports(tmp_path, capsys):
    previous = tmp_path / "previous.csv"
    current = tmp_path / "current.csv"
    previous.write_bytes(csv_bytes(previous_rows()))
    current.write_bytes(csv_bytes(current_rows()))
    output = tmp_path / "out"

    exit_code = main([str(previous), str(current), "--output-dir", str(output)])

    assert exit_code == 0
    assert (output / "reconciliation_report.csv").exists()
    assert (output / "review_required.csv").exists()
    assert "Records requiring review: 4" in capsys.readouterr().out


def test_cli_reports_bad_input_without_a_traceback(tmp_path, capsys):
    previous = tmp_path / "previous.csv"
    previous.write_bytes(b"")
    current = tmp_path / "current.csv"
    current.write_bytes(csv_bytes(current_rows()))

    exit_code = main([str(previous), str(current), "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert "empty" in capsys.readouterr().err
