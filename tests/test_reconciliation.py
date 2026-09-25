"""Cross-cycle reconciliation: lifecycle, salary, IBAN, contract and date changes."""

from __future__ import annotations

import json

import pytest

from src.models import Category, Severity
from src.reconciliation import reconcile, salary_change_severity
from src.validators import validate_dataset
from tests.conftest import employee


def reconcile_rows(make_loaded, rules, previous_rows, current_rows):
    previous = validate_dataset(make_loaded(previous_rows, "previous"), rules)
    current = validate_dataset(make_loaded(current_rows, "current"), rules)
    return reconcile(previous, current, rules)


def only(issues, rule: str):
    matching = [issue for issue in issues if issue.rule == rule]
    assert len(matching) == 1, f"expected exactly one {rule} issue, got {matching}"
    return matching[0]


# --- lifecycle -----------------------------------------------------------------


def test_unchanged_record_produces_no_issues(make_loaded, rules):
    assert reconcile_rows(make_loaded, rules, [employee()], [employee()]) == []


def test_new_record_is_detected(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee()], [employee(), employee(employee_id="EMP-00002", first_name="Bea")]
    )

    issue = only(issues, "new_record")
    assert issue.employee_id == "EMP-00002"
    assert issue.category is Category.LIFECYCLE
    assert issue.dataset == "current"
    assert issue.severity is rules.lifecycle.new_record.severity
    assert issue.requires_review is False
    assert "Bea Rossi" in issue.message


def test_removed_record_is_detected(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(), employee(employee_id="EMP-00002")], [employee()]
    )

    issue = only(issues, "removed_record")
    assert issue.employee_id == "EMP-00002"
    assert issue.dataset == "previous"
    assert issue.severity is Severity.WARNING
    assert issue.requires_review is True


def test_records_without_a_key_are_not_matched(make_loaded, rules):
    issues = reconcile_rows(make_loaded, rules, [employee()], [employee(), employee(employee_id="")])

    assert [issue.rule for issue in issues] == []


def test_duplicate_key_is_excluded_from_comparison(make_loaded, rules):
    current = [employee(monthly_salary="2100"), employee(monthly_salary="9000")]

    issues = reconcile_rows(make_loaded, rules, [employee()], current)

    assert [issue.rule for issue in issues] == []


# --- salary --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (0.0, Severity.INFO),
        (14.99, Severity.INFO),
        (15.0, Severity.INFO),  # boundary: "<= 15%" is informational
        (15.01, Severity.WARNING),
        (-15.01, Severity.WARNING),  # decreases count by magnitude
        (30.0, Severity.WARNING),  # boundary: exactly 30% is still a warning
        (30.01, Severity.CRITICAL),
        (-42.86, Severity.CRITICAL),
        (900.0, Severity.CRITICAL),
    ],
)
def test_salary_change_thresholds(change, expected, rules):
    assert salary_change_severity(change, rules) is expected


def test_salary_increase_is_reported_with_percentage(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="2100")], [employee(monthly_salary="3000")]
    )

    issue = only(issues, "salary_change")
    assert issue.category is Category.SALARY_CHANGE
    assert issue.previous_value == 2100.0
    assert issue.current_value == 3000.0
    assert issue.change_percentage == pytest.approx(42.857143)
    assert issue.severity is Severity.CRITICAL
    assert issue.requires_review is True
    assert "increased by 42.86%" in issue.message


def test_salary_decrease_within_tolerance_is_info(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="2000")], [employee(monthly_salary="1800")]
    )

    issue = only(issues, "salary_change")
    assert issue.change_percentage == -10.0
    assert issue.severity is Severity.INFO
    assert issue.requires_review is False
    assert "decreased by 10.00%" in issue.message


def test_salary_from_zero_has_no_percentage(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="0")], [employee(monthly_salary="2000")]
    )

    issue = only(issues, "salary_change")
    assert issue.change_percentage is None
    assert issue.severity is Severity.WARNING


def test_salary_previously_missing_is_informational(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="")], [employee(monthly_salary="2000")]
    )

    issue = only(issues, "salary_change")
    assert issue.severity is Severity.INFO
    assert issue.previous_value is None


def test_missing_current_salary_is_not_a_change(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="2000")], [employee(monthly_salary="")]
    )

    assert [issue.rule for issue in issues if issue.rule == "salary_change"] == []


# --- IBAN ----------------------------------------------------------------------


def test_iban_change_is_critical_and_masked(make_loaded, rules):
    old, new = "IT60X0542811101000000123456", "DE89370400440532013000"
    issues = reconcile_rows(make_loaded, rules, [employee(iban=old)], [employee(iban=new)])

    issue = only(issues, "iban_change")
    assert issue.category is Category.IBAN_CHANGE
    assert issue.severity is Severity.CRITICAL
    assert issue.requires_review is True
    assert issue.previous_value == "IT60X****3456"
    assert issue.current_value == "DE893****3000"
    serialized = json.dumps(issue.model_dump(mode="json"))
    assert old not in serialized and new not in serialized


def test_iban_formatting_differences_are_not_changes(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded,
        rules,
        [employee(iban="IT60X0542811101000000123456")],
        [employee(iban="it60 x054 2811 1010 0000 0123 456")],
    )

    assert issues == []


def test_iban_added_is_reported(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(iban="")], [employee(iban="IT60X0542811101000000123456")]
    )

    issue = only(issues, "iban_change")
    assert issue.previous_value is None
    assert "added" in issue.message


# --- contract fields -------------------------------------------------------------


def test_contract_type_change_is_a_warning(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(contract_type="part_time")], [employee(contract_type="full_time")]
    )

    issue = only(issues, "contract_type_change")
    assert issue.category is Category.CONTRACT_CHANGE
    assert issue.severity is Severity.WARNING
    assert issue.requires_review is True
    assert issue.previous_value == "part_time" and issue.current_value == "full_time"


def test_working_hours_change_carries_a_percentage(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(working_hours="40")], [employee(working_hours="32")]
    )

    issue = only(issues, "working_hours_change")
    assert issue.change_percentage == -20.0
    assert issue.severity is Severity.WARNING


def test_department_change_is_informational(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(department="Sales")], [employee(department="Finance")]
    )

    issue = only(issues, "department_change")
    assert issue.severity is Severity.INFO
    assert issue.requires_review is False


def test_text_comparison_ignores_case_and_whitespace(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(contract_type="Full_Time ")], [employee(contract_type="full_time")]
    )

    assert issues == []


# --- dates ---------------------------------------------------------------------


def test_start_date_change_is_reported(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(start_date="2020-01-15")], [employee(start_date="2020-02-01")]
    )

    issue = only(issues, "start_date_changed")
    assert issue.category is Category.LIFECYCLE
    assert issue.previous_value == "2020-01-15" and issue.current_value == "2020-02-01"
    assert issue.severity is Severity.WARNING


def test_end_date_added_is_reported(make_loaded, rules):
    issues = reconcile_rows(make_loaded, rules, [employee(end_date="")], [employee(end_date="2024-12-31")])

    issue = only(issues, "end_date_added")
    assert issue.current_value == "2024-12-31"
    assert issue.requires_review is True


def test_end_date_changed_is_reported(make_loaded, rules):
    issues = reconcile_rows(
        make_loaded, rules, [employee(end_date="2024-11-30")], [employee(end_date="2024-12-31")]
    )

    only(issues, "end_date_changed")


def test_date_that_becomes_unparseable_is_reported_as_emptied(make_loaded, rules):
    # The validators report the invalid date itself; reconciliation still reports
    # that the usable value disappeared, so the record shows up even if
    # start_date is not a required field.
    issues = reconcile_rows(
        make_loaded, rules, [employee(start_date="2020-01-15")], [employee(start_date="2024-02-30")]
    )

    issue = only(issues, "start_date_changed")
    assert issue.previous_value == "2020-01-15"
    assert issue.current_value is None
    assert "to empty" in issue.message


def test_salary_message_shows_extra_precision_only_when_it_matters(make_loaded, rules):
    boundary = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="2000")], [employee(monthly_salary="2300.002")]
    )
    ordinary = reconcile_rows(
        make_loaded, rules, [employee(monthly_salary="2100")], [employee(monthly_salary="3000")]
    )

    assert only(boundary, "salary_change").severity is Severity.WARNING
    assert "increased by 15.0001%" in only(boundary, "salary_change").message
    assert "increased by 42.86%" in only(ordinary, "salary_change").message
