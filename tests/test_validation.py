"""Single-dataset validation: required fields, duplicates, types and impossible values."""

from __future__ import annotations

import math

from src.models import Category, Severity
from src.validators import validate_dataset
from tests.conftest import employee


def rules_of(issues, rule: str):
    return [issue for issue in issues if issue.rule == rule]


def test_clean_dataset_produces_no_issues(make_loaded, rules):
    rows = [
        employee(),
        employee(employee_id="EMP-00002", email="b@example.com", iban="IT00X0000000000000000000002"),
    ]
    validated = validate_dataset(make_loaded(rows), rules)

    assert validated.issues == []
    assert validated.frame["monthly_salary"].dtype == "float64"


# --- required fields ---------------------------------------------------------


def test_missing_required_fields_are_reported_per_field(make_loaded, rules):
    loaded = make_loaded([employee(last_name="", monthly_salary="")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "missing_required_field")

    assert sorted(issue.field for issue in issues) == ["last_name", "monthly_salary"]
    assert all(issue.category is Category.MISSING_DATA for issue in issues)
    assert all(issue.severity is rules.missing_data.severity for issue in issues)
    assert all(issue.employee_id == "EMP-00001" for issue in issues)


def test_missing_employee_id_is_reported_by_row_number(make_loaded, rules):
    loaded = make_loaded([employee(), employee(employee_id="")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "missing_required_field")

    assert len(issues) == 1
    assert issues[0].employee_id is None
    assert issues[0].row_number == 3
    assert issues[0].record_label == "row 3"


def test_optional_fields_are_not_required(make_loaded, rules):
    loaded = make_loaded([employee(email="", iban="", bonus="", department="")])

    assert rules_of(validate_dataset(loaded, rules).issues, "missing_required_field") == []


# --- duplicates ----------------------------------------------------------------


def test_duplicate_employee_id_is_critical_and_reported_once(make_loaded, rules):
    loaded = make_loaded([employee(), employee(monthly_salary="2500"), employee(employee_id="EMP-00002")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "duplicate_employee_id")

    assert len(issues) == 1
    assert issues[0].severity is Severity.CRITICAL
    assert issues[0].requires_review is True
    assert issues[0].employee_id == "EMP-00001"
    assert "rows 2, 3" in issues[0].message


def test_duplicate_email_is_case_insensitive_and_reported_per_record(make_loaded, rules):
    loaded = make_loaded(
        [
            employee(email="Shared@Example.com"),
            employee(employee_id="EMP-00002", email="shared@example.com", iban="IT00X0000000000000000000002"),
        ]
    )

    issues = rules_of(validate_dataset(loaded, rules).issues, "duplicate_email")

    assert sorted(issue.employee_id for issue in issues) == ["EMP-00001", "EMP-00002"]
    assert all(issue.severity is rules.duplicates.email for issue in issues)
    assert "EMP-00002" in issues[0].message


def test_same_record_exported_twice_is_only_a_duplicate_key_issue(make_loaded, rules):
    loaded = make_loaded([employee(), employee(monthly_salary="2350")])

    issues = validate_dataset(loaded, rules).issues

    assert [issue.rule for issue in issues] == ["duplicate_employee_id"]


def test_duplicate_iban_never_exposes_the_full_iban(make_loaded, rules):
    iban = "IT60X0542811101000000123456"
    loaded = make_loaded(
        [
            employee(iban=iban),
            employee(employee_id="EMP-00002", email="b@example.com", iban="it60 x054 2811 1010 0000 0123 456"),
        ]
    )

    issues = rules_of(validate_dataset(loaded, rules).issues, "duplicate_iban")

    assert len(issues) == 2
    for issue in issues:
        assert issue.current_value == "IT60X****3456"
        assert iban not in issue.message
        assert iban not in str(issue.current_value)


# --- types ---------------------------------------------------------------------


def test_non_numeric_salary_is_reported_and_becomes_nan(make_loaded, rules):
    loaded = make_loaded([employee(monthly_salary="two thousand")])

    validated = validate_dataset(loaded, rules)

    issues = rules_of(validated.issues, "invalid_number")
    assert len(issues) == 1
    assert issues[0].field == "monthly_salary"
    assert issues[0].current_value == "two thousand"
    assert math.isnan(validated.frame.loc[0, "monthly_salary"])
    # not double-reported as missing
    assert rules_of(validated.issues, "missing_required_field") == []


def test_impossible_date_is_reported(make_loaded, rules):
    loaded = make_loaded([employee(start_date="2024-02-30")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "invalid_date")

    assert len(issues) == 1
    assert issues[0].field == "start_date"
    assert issues[0].severity is rules.invalid_values.severity


def test_wrong_date_format_is_reported(make_loaded, rules):
    loaded = make_loaded([employee(start_date="15/01/2020")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "invalid_date")

    assert len(issues) == 1
    assert "%Y-%m-%d" in issues[0].message


# --- impossible values ---------------------------------------------------------


def test_negative_salary_is_critical(make_loaded, rules):
    loaded = make_loaded([employee(monthly_salary="-100")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "negative_salary")

    assert len(issues) == 1
    assert issues[0].severity is Severity.CRITICAL
    assert issues[0].current_value == -100.0


def test_end_date_before_start_date_is_reported(make_loaded, rules):
    loaded = make_loaded([employee(start_date="2022-05-01", end_date="2021-01-31")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "end_before_start")

    assert len(issues) == 1
    assert issues[0].field == "end_date"
    assert "2021-01-31" in issues[0].message


def test_end_date_after_start_date_is_fine(make_loaded, rules):
    loaded = make_loaded([employee(start_date="2022-05-01", end_date="2023-01-31")])

    assert rules_of(validate_dataset(loaded, rules).issues, "end_before_start") == []


def test_malformed_email_is_a_warning(make_loaded, rules):
    loaded = make_loaded([employee(email="ada.rossi-at-example.com")])

    issues = rules_of(validate_dataset(loaded, rules).issues, "malformed_email")

    assert len(issues) == 1
    assert issues[0].severity is Severity.WARNING
    assert issues[0].requires_review is True


def test_issue_slot_follows_dataset_name(make_loaded, rules):
    previous = validate_dataset(make_loaded([employee(monthly_salary="-1")], name="previous"), rules)
    current = validate_dataset(make_loaded([employee(monthly_salary="-1")], name="current"), rules)

    assert previous.issues[0].previous_value == -1.0 and previous.issues[0].current_value is None
    assert current.issues[0].current_value == -1.0 and current.issues[0].previous_value is None
