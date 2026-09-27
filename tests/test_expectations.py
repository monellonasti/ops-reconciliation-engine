"""Expected changes: matching, mismatches, missing approvals, loading and privacy."""

from __future__ import annotations

import pytest

from src.config import Rules, rules_from_dict
from src.engine import main, reconcile_sources
from src.expectations import EXPECTABLE_FIELDS, load_expected_changes, values_equal
from src.loader import DatasetLoadError
from src.models import Category, ReviewStatus, Severity
from src.reporting import full_report_csv
from tests.conftest import csv_bytes, employee

HEADER = "employee_id,field,expected_value,reference\n"


def expected_csv(*rows: str) -> bytes:
    return (HEADER + "".join(row + "\n" for row in rows)).encode("utf-8")


def run(previous_rows, current_rows, expected: bytes | None, rules: Rules | None = None):
    return reconcile_sources(csv_bytes(previous_rows), csv_bytes(current_rows), rules or Rules(), expected_source=expected)


def only(result, rule: str):
    matching = [issue for issue in result.issues if issue.rule == rule]
    assert len(matching) == 1, f"expected one {rule} finding, got {matching}"
    return matching[0]


# --- matching ----------------------------------------------------------------------


def test_matching_salary_change_is_downgraded_to_info_and_marked():
    result = run(
        [employee(monthly_salary="2100")],
        [employee(monthly_salary="3000")],
        expected_csv("EMP-00001,monthly_salary,3000,HR-2024-118"),
    )

    issue = only(result, "salary_change")
    assert issue.severity is Severity.INFO
    assert issue.requires_review is False
    assert issue.expected_reference == "HR-2024-118"
    assert issue.expected_mismatch is None
    assert "Matches expected change (HR-2024-118)" in issue.message
    assert issue.change_percentage == pytest.approx(42.857143)  # the fact is unchanged
    assert result.summary.expected_matched == 1
    assert result.summary.records_requiring_review == 0
    assert result.review_queue == []


def test_review_policy_still_applies_to_downgraded_findings():
    rules = rules_from_dict({"review_policy": {"info": True, "warning": True, "critical": True}})

    result = run(
        [employee(monthly_salary="2100")],
        [employee(monthly_salary="3000")],
        expected_csv("EMP-00001,monthly_salary,3000,HR-2024-118"),
        rules,
    )

    assert only(result, "salary_change").requires_review is True


@pytest.mark.parametrize(
    ("field", "before", "after", "expected_text", "rule"),
    [
        ("contract_type", "part_time", "full_time", "Full_Time", "contract_type_change"),
        ("working_hours", "20", "40", "40.0", "working_hours_change"),
        ("department", "Sales", "Finance", "finance", "department_change"),
        ("start_date", "2020-01-15", "2020-02-01", "2020-02-01", "start_date_changed"),
        ("end_date", "", "2024-12-31", "2024-12-31", "end_date_added"),
        ("end_date", "2024-11-30", "2024-12-31", "2024-12-31", "end_date_changed"),
    ],
)
def test_every_comparable_field_can_be_expected(field, before, after, expected_text, rule):
    result = run(
        [employee(**{field: before})],
        [employee(**{field: after})],
        expected_csv(f"EMP-00001,{field},{expected_text},ticket-1"),
    )

    issue = only(result, rule)
    assert issue.severity is Severity.INFO
    assert issue.expected_reference == "ticket-1"


def test_expected_iban_change_stays_critical_but_is_marked():
    new_iban = "DE89370400440532013000"
    result = run(
        [employee()],
        [employee(iban=new_iban)],
        expected_csv(f"EMP-00001,iban,{new_iban},request 2024-09-02"),
    )

    issue = only(result, "iban_change")
    assert issue.severity is Severity.CRITICAL
    assert issue.requires_review is True
    assert issue.expected_reference == "request 2024-09-02"
    assert "IBAN changes are always reviewed" in issue.message
    assert new_iban not in issue.model_dump_json()
    assert new_iban not in full_report_csv(result).decode("utf-8-sig")


def test_iban_expectation_matches_on_the_full_normalized_value():
    result = run(
        [employee()],
        [employee(iban="DE89 3704 0044 0532 0130 00")],
        expected_csv("EMP-00001,iban,de89370400440532013000,ok"),
    )

    assert only(result, "iban_change").expected_reference == "ok"


def test_expected_new_and_removed_records():
    first, second = employee(), employee(employee_id="EMP-00002", email="b@example.com", iban="")
    result = run(
        [first],
        [first, second],
        expected_csv("EMP-00002,new_record,,offer signed"),
    )
    assert only(result, "new_record").expected_reference == "offer signed"
    assert result.summary.expected_missing == 0

    result = run(
        [first, second],
        [first],
        expected_csv("EMP-00002,removed_record,,leaver 2024-09"),
    )
    removed = only(result, "removed_record")
    assert removed.severity is Severity.INFO
    assert removed.requires_review is False


# --- mismatches and missing approvals ------------------------------------------------


def test_change_to_a_different_value_keeps_severity_and_says_what_was_expected():
    result = run(
        [employee(monthly_salary="2000")],
        [employee(monthly_salary="2440")],  # +22%
        expected_csv("EMP-00001,monthly_salary,2400,HR-2024-140"),
    )

    issue = only(result, "salary_change")
    assert issue.severity is Severity.WARNING
    assert issue.requires_review is True
    assert issue.expected_reference is None
    assert issue.expected_mismatch == "2,400"
    assert "Differs from the expected value 2,400 (HR-2024-140)" in issue.message
    assert result.summary.expected_mismatched == 1
    assert result.summary.expected_missing == 0


def test_approved_change_that_did_not_happen_is_a_finding():
    result = run(
        [employee(department="Sales")],
        [employee(department="Sales")],
        expected_csv("EMP-00001,department,Finance,transfer request"),
    )

    issue = only(result, "expected_change_missing")
    assert issue.category is Category.EXPECTED_CHANGE
    assert issue.severity is Severity.WARNING
    assert issue.requires_review is True
    assert issue.employee_id == "EMP-00001"
    assert issue.field == "department"
    assert issue.current_value == "Sales"
    assert issue.expected_mismatch == "Finance"
    assert "Expected department to become Finance (transfer request) but the current value is Sales" in issue.message
    assert result.summary.expected_missing == 1
    assert result.summary.expected_mismatched == 0


def test_missing_severity_is_configurable():
    rules = rules_from_dict({"expected_changes": {"missing_severity": "info"}})

    result = run([employee()], [employee()], expected_csv("EMP-00001,department,Finance,ref"), rules)

    assert only(result, "expected_change_missing").severity is Severity.INFO


def test_value_already_in_place_is_not_reported_as_missing():
    result = run(
        [employee(department="Finance")],
        [employee(department="Finance")],
        expected_csv("EMP-00001,department,Finance,applied last month"),
    )

    assert result.issues == []


@pytest.mark.parametrize(
    ("previous_rows", "current_rows", "row", "fragment"),
    [
        ([employee()], [employee()], "EMP-00009,monthly_salary,3000,ref", "not present in either cycle"),
        ([employee(), employee(employee_id="EMP-00009", email="x@example.com", iban="")], [employee()],
         "EMP-00009,monthly_salary,3000,ref", "absent from the current cycle"),
        ([employee()], [employee()], "EMP-00009,new_record,,ref", "not present in the current cycle"),
        ([employee()], [employee()], "EMP-00001,new_record,,ref", "already existed in the previous cycle"),
        ([employee()], [employee()], "EMP-00001,removed_record,,ref", "still present in the current cycle"),
        ([employee()], [employee()], "EMP-00009,removed_record,,ref", "not present in the previous cycle either"),
    ],
)
def test_missing_messages_explain_what_was_found_instead(previous_rows, current_rows, row, fragment):
    result = run(previous_rows, current_rows, expected_csv(row))

    assert fragment in only(result, "expected_change_missing").message


def test_expected_iban_that_did_not_change_is_masked_in_the_finding():
    result = run(
        [employee()],
        [employee()],
        expected_csv("EMP-00001,iban,DE89370400440532013000,ref"),
    )

    issue = only(result, "expected_change_missing")
    assert "DE89370400440532013000" not in issue.model_dump_json()
    assert "DE893****3000" in issue.message
    assert issue.current_value == "IT60X****3456"


def test_notes_summarise_the_expectations():
    result = run(
        [employee(monthly_salary="2000", department="Sales")],
        [employee(monthly_salary="2200", department="Sales")],
        expected_csv("EMP-00001,monthly_salary,2200,a", "EMP-00001,department,Finance,b"),
    )

    assert any("Expected changes: 2 listed, 1 matched" in note and "1 not found" in note for note in result.notes)


def test_history_decisions_still_apply_to_expected_findings(tmp_path):
    from src.history import ReviewHistory

    history = ReviewHistory(tmp_path / "h.sqlite")
    expected = expected_csv("EMP-00001,department,Finance,ref")
    first = reconcile_sources(csv_bytes([employee()]), csv_bytes([employee()]), Rules(), expected_source=expected)
    history.record(only(first, "expected_change_missing"), ReviewStatus.ACCEPTED, note="postponed")

    second = reconcile_sources(csv_bytes([employee()]), csv_bytes([employee()]), Rules(), history, expected)

    assert only(second, "expected_change_missing").review_status is ReviewStatus.ACCEPTED
    assert second.summary.records_requiring_review == 0


# --- loading -----------------------------------------------------------------------


def test_loader_normalises_and_keeps_references():
    changes = load_expected_changes(expected_csv(" EMP-00001 , Monthly_Salary , 3000 , HR-1 ", "EMP-00002,new_record,,"))

    assert len(changes) == 2
    salary = changes.lookup("EMP-00001", "monthly_salary")
    assert salary is not None and salary.expected_value == "3000" and salary.reference == "HR-1"
    assert changes.lookup("EMP-00002", "new_record").reference is None
    assert changes.lookup("EMP-00002", "new_record").label == "expected changes row 3"


def test_loader_accepts_the_optional_reference_column_being_absent():
    changes = load_expected_changes(b"employee_id,field,expected_value\nEMP-00001,department,Finance\n")

    assert changes.lookup("EMP-00001", "department").reference is None


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        (b"employee_id,field\nEMP-1,department\n", "missing column.*expected_value"),
        (expected_csv(",department,Finance,ref"), "row 2: employee_id is empty"),
        (expected_csv("EMP-1,first_name,Ada,ref"), "field 'first_name' is not one of"),
        (expected_csv("EMP-1,department,,ref"), "expected_value is required for department"),
        (expected_csv("EMP-1,new_record,yes,ref"), "expected_value must be empty for new_record"),
        (expected_csv("EMP-1,department,Finance,a", "EMP-1,department,Sales,b"), "listed more than once"),
        (expected_csv("EMP-1,department,Finance,a", "EMP-2,department,Sales,b,EXTRA"), "wrong number of fields"),
        (b"", "empty"),
    ],
)
def test_loader_rejects_unusable_files_with_a_clear_message(content, fragment):
    with pytest.raises(DatasetLoadError, match=fragment):
        load_expected_changes(content)


def test_loader_reports_several_problems_at_once():
    with pytest.raises(DatasetLoadError) as info:
        load_expected_changes(expected_csv(",department,Finance,a", "EMP-1,bonus,10,b"))

    assert "row 2" in str(info.value) and "row 3" in str(info.value)


def test_allowed_fields_are_documented():
    assert set(EXPECTABLE_FIELDS) == {
        "monthly_salary", "iban", "contract_type", "working_hours", "department",
        "start_date", "end_date", "new_record", "removed_record",
    }


# --- value comparison ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "expected", "actual", "equal"),
    [
        ("monthly_salary", "2400", 2400.0, True),
        ("monthly_salary", "2400.00", 2400.0, True),
        ("monthly_salary", "2400", 2401.0, False),
        ("monthly_salary", "abc", 2400.0, False),
        ("working_hours", "40", 40.0, True),
        ("department", "Finance", "finance ", True),
        ("department", "Finance", "Sales", False),
        ("iban", "de89 3704 0044 0532 0130 00", "DE89370400440532013000", True),
        ("start_date", "2024-02-30", None, False),
        ("end_date", None, None, True),
        ("end_date", "2024-12-31", None, False),
    ],
)
def test_values_equal(field, expected, actual, equal):
    assert values_equal(field, expected, actual, Rules()) is equal


def test_dates_compare_on_the_day():
    import pandas as pd

    assert values_equal("start_date", "2024-12-31", pd.Timestamp("2024-12-31"), Rules())
    assert not values_equal("start_date", "2024-12-30", pd.Timestamp("2024-12-31"), Rules())
    assert values_equal("start_date", "31/12/2024", pd.Timestamp("2024-12-31"), Rules())  # accepted input format
    assert not values_equal("start_date", "2024/12/31", pd.Timestamp("2024-12-31"), Rules())


# --- command line --------------------------------------------------------------------


def test_cli_accepts_an_expected_changes_file(tmp_path, capsys):
    previous, current, expected = tmp_path / "p.csv", tmp_path / "c.csv", tmp_path / "e.csv"
    previous.write_bytes(csv_bytes([employee(monthly_salary="2100")]))
    current.write_bytes(csv_bytes([employee(monthly_salary="3000")]))
    expected.write_bytes(expected_csv("EMP-00001,monthly_salary,3000,HR-1"))
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("history:\n  enabled: false\n", encoding="utf-8")

    exit_code = main([str(previous), str(current), "--rules", str(rules_file), "--expected", str(expected),
                      "--output-dir", str(tmp_path / "out")])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Records requiring review: 0" in output
    assert "Expected changes: 1 listed, 1 matched" in output


def test_cli_reports_a_bad_expected_changes_file(tmp_path, capsys):
    previous = tmp_path / "p.csv"
    previous.write_bytes(csv_bytes([employee()]))
    expected = tmp_path / "e.csv"
    expected.write_bytes(expected_csv("EMP-1,bonus,10,ref"))

    exit_code = main([str(previous), str(previous), "--expected", str(expected), "--output-dir", str(tmp_path)])

    assert exit_code == 1
    assert "Expected changes file" in capsys.readouterr().err
