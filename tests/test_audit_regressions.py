"""CSV-to-report scenarios and regressions discovered during the implementation audit."""

import io

import pandas as pd
import pytest

import app
from src.config import Rules, RulesConfigError, load_rules, rules_from_dict
from src.engine import main, reconcile_sources
from src.loader import DatasetLoadError, load_dataset
from src.models import EXPECTED_COLUMNS
from src.reporting import full_report_csv, review_queue_csv
from tests.conftest import csv_bytes, employee


def run(before, after, rules=None):
    return reconcile_sources(csv_bytes(before), csv_bytes(after), rules or Rules())


@pytest.mark.parametrize(("changes", "rule", "severity"), [
    ({}, None, None),
    ({"monthly_salary": "2200"}, "salary_change", "info"),
    ({"monthly_salary": "2400"}, "salary_change", "warning"),
    ({"monthly_salary": "2800"}, "salary_change", "critical"),
    ({"iban": "DE89370400440532013000"}, "iban_change", "critical"),
    ({"bonus": "1200"}, "bonus_ratio", "warning"),
    ({"bonus": "2400"}, "bonus_ratio", "critical"),
    ({"overtime_hours": "-1"}, "overtime_hours", "critical"),
    ({"overtime_hours": "80"}, "overtime_hours", "warning"),
    ({"overtime_hours": "120"}, "overtime_hours", "critical"),
    ({"end_date": "2019-01-01"}, "end_before_start", "critical"),
    ({"email": "bad-email"}, "malformed_email", "warning"),
])
def test_manual_scenarios_a_to_o(changes, rule, severity):
    base = employee(monthly_salary="2000")
    result = run([base], [dict(base, **changes)])
    if rule is None:
        assert result.issues == []
    else:
        issue = next(i for i in result.issues if i.rule == rule)
        assert issue.severity == severity
        if rule == "iban_change":
            assert issue.requires_review
            assert "DE89370400440532013000" not in full_report_csv(result).decode()


@pytest.mark.parametrize(("salary", "severity"), [
    ("2300", "info"), ("2300.002", "warning"),
    ("2600", "warning"), ("2600.002", "critical"),
    ("1700", "info"), ("1699.998", "warning"),
    ("1400", "warning"), ("1399.998", "critical"),
])
def test_salary_precision_boundaries(salary, severity):
    result = run([employee(monthly_salary="2000")], [employee(monthly_salary=salary)])
    assert result.issues[0].severity == severity


def test_exact_decimal_salary_boundary_does_not_round_up():
    result = run([employee(monthly_salary="0.07")], [employee(monthly_salary="0.0805")])
    assert result.issues[0].severity == "info"


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("bonus", "1000", None), ("bonus", "1000.0001", "warning"),
    ("bonus", "2000", "warning"), ("bonus", "2000.0001", "critical"),
    ("overtime_hours", "0", None), ("overtime_hours", "-0.0001", "critical"),
    ("overtime_hours", "60", None), ("overtime_hours", "60.0001", "warning"),
    ("overtime_hours", "100", "warning"), ("overtime_hours", "100.0001", "critical"),
])
def test_bonus_overtime_boundaries(field, value, expected):
    base = employee(monthly_salary="2000")
    result = run([base], [dict(base, **{field: value})])
    assert [i.severity.value for i in result.issues] == ([] if expected is None else [expected])


def test_new_removed_and_duplicate_scenarios():
    first, second = employee(), employee(employee_id="EMP-2", email="b@example.com", iban="")
    assert run([first], [first, second]).summary.new_records == 1
    assert run([first, second], [first]).summary.removed_records == 1
    for current in ([first, employee(monthly_salary="9000")], [employee(monthly_salary="9000"), first]):
        result = run([first], current)
        assert [i.rule for i in result.issues] == ["duplicate_employee_id"]
        assert result.issues[0].severity == "critical" and result.issues[0].requires_review
    assert not any(i.rule in {"new_record", "removed_record"}
                   for i in run([first, first], [second]).issues if i.employee_id == first["employee_id"])


@pytest.mark.parametrize("column", ["iban", "department", "working_hours", "start_date", "end_date"])
@pytest.mark.parametrize("side", ["previous", "current"])
def test_missing_optional_column_does_not_fabricate_change(column, side):
    base = employee(end_date="2025-01-01")
    full = csv_bytes([base])
    partial = csv_bytes([base], [c for c in EXPECTED_COLUMNS if c != column])
    result = reconcile_sources(partial if side == "previous" else full,
                               partial if side == "current" else full)
    assert result.issues == []
    assert result.notes


@pytest.mark.parametrize("column", ["monthly_salary", "bonus", "working_hours", "overtime_hours"])
@pytest.mark.parametrize("value", ["inf", "-inf", "NaN"])
def test_nonfinite_numeric_is_invalid(column, value):
    result = run([employee()], [employee(**{column: value})])
    assert any(i.rule == "invalid_number" and i.field == column for i in result.issues)
    assert "Infinity" not in result.model_dump_json()


@pytest.mark.parametrize("raw", [
    b'employee_id,first_name,last_name,contract_type,monthly_salary\nEMP-1,A,B,full_time,"2000',
    b'employee_id,first_name,last_name,contract_type,monthly_salary\nEMP-1,A,B,full_time,2000\x00',
])
def test_malformed_csv_is_rejected(raw):
    with pytest.raises(DatasetLoadError):
        load_dataset(raw, name="current", rules=Rules())


@pytest.mark.parametrize("config", [
    {"iban_change": {"severity": "info"}}, {"iban_change": {"requires_review": False}},
    {"duplicates": {"employee_id": "warning"}},
    {"salary_change": {"critical_percentage": float("inf")}},
    {"bonus": {"critical_salary_ratio": float("nan")}},
])
def test_unsafe_configuration_rejected(config):
    with pytest.raises(RulesConfigError):
        rules_from_dict(config)


@pytest.mark.parametrize("content", [b'\xff', b'false', b'[]'])
def test_invalid_config_is_operator_error(tmp_path, content):
    path = tmp_path / "rules.yaml"
    path.write_bytes(content)
    with pytest.raises(RulesConfigError):
        load_rules(path)


def test_yaml_changes_actual_pipeline(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("salary_change:\n  warning_percentage: 5\n  critical_percentage: 10\n"
                    "bonus:\n  warning_salary_ratio: 0.1\n"
                    "overtime:\n  warning_hours: 3\n"
                    "required_fields: [employee_id, email]\n"
                    "review_policy:\n  info: true\n", encoding="utf-8")
    base = employee(monthly_salary="2000")
    result = run([base], [dict(base, monthly_salary="2200", bonus="500", email="", department="HR")], load_rules(path))
    rules = {i.rule: i for i in result.issues}
    assert rules["salary_change"].severity == "warning"
    assert rules["bonus_ratio"].severity == "warning"
    assert rules["overtime_hours"].severity == "warning"
    assert rules["missing_required_field"].field == "email"
    assert rules["department_change"].requires_review


@pytest.mark.parametrize("field", ["monthly_salary", "start_date", "email", "department", "first_name"])
def test_misplaced_iban_not_exposed(field):
    secret = "DE89370400440532013000"
    result = run([employee()], [employee(**{field: secret}), employee(employee_id="EMP-2", **{field: secret})])
    for output in (full_report_csv(result), review_queue_csv(result), result.model_dump_json().encode()):
        assert secret.encode() not in output


def test_configured_fields_masked_in_messages_and_values():
    rules = Rules(masked_fields=["first_name", "department", "email"])
    result = run([employee()], [employee(department="SecretDept", email="SecretMail"),
                                employee(employee_id="EMP-2", first_name="SecretName")], rules)
    output = full_report_csv(result).decode()
    assert not any(s in output for s in ("SecretDept", "SecretMail", "SecretName"))
    assert "iban" in rules.masked_fields
    result = run([employee()], [employee(iban="DE89370400440532013000")], Rules(masked_fields=[]))
    assert "DE89370400440532013000" not in result.model_dump_json()


def test_keyless_review_count_is_per_cycle():
    result = run([employee(employee_id="")], [employee(employee_id="")])
    assert result.summary.records_requiring_review == 2


@pytest.mark.parametrize("formula", ["=1+1", "+1+1", "-1+1", "@SUM(1)", "\t=1+1"])
def test_spreadsheet_export_treats_text_as_literal(formula):
    result = run([employee()], [employee(employee_id=formula)])
    exported = pd.read_csv(io.BytesIO(full_report_csv(result)), keep_default_na=False)
    assert "'" + formula.strip() in set(exported.employee_id)


def test_failed_rerun_clears_old_result(monkeypatch):
    state = {}
    monkeypatch.setattr(app.st, "session_state", state)
    app.run_pipeline(csv_bytes([employee()]), csv_bytes([employee()]), "p", "c", Rules())
    assert "result" in state
    app.run_pipeline(b"", b"", "bad", "bad", Rules())
    assert "error" in state and "result" not in state and "previous" not in state


def test_exception_values_not_logged(monkeypatch, caplog):
    monkeypatch.setattr(app.st, "session_state", {})
    def fail(*args):
        raise RuntimeError("PrivateValue")
    monkeypatch.setattr(app, "run_reconciliation", fail)
    app.run_pipeline(csv_bytes([employee()]), csv_bytes([employee()]), "p", "c", Rules())
    assert "PrivateValue" not in caplog.text


def test_snapshot_detects_change_despite_mask_collision(monkeypatch):
    monkeypatch.setattr(app.st, "session_state", {})
    before = employee(iban="IT60X0542811101000000123456")
    after = employee(iban="IT60X9999911101000000123456")
    app.run_pipeline(csv_bytes([before]), csv_bytes([after]), "p", "c", Rules())
    issue = app.st.session_state["result"].issues[0]
    snapshot = app.record_snapshot(issue, Rules())
    row = snapshot[snapshot.Field == "iban"].iloc[0]
    assert row.Previous == row.Current and row.Changed == "yes"


def test_duplicate_snapshot_contains_all_candidates(monkeypatch):
    monkeypatch.setattr(app.st, "session_state", {})
    app.run_pipeline(csv_bytes([employee()]), csv_bytes([employee(), employee(monthly_salary="9000")]), "p", "c", Rules())
    snapshot = app.record_snapshot(app.st.session_state["result"].issues[0], Rules())
    assert len(snapshot) == 3
    assert set(snapshot.monthly_salary) == {"2100", "9000"}


def test_cli_output_error_is_clean(tmp_path, capsys):
    source = tmp_path / "data.csv"
    source.write_bytes(csv_bytes([employee()]))
    assert main([str(source), str(source), "--output-dir", str(source)]) == 1
    assert "Could not write both reports" in capsys.readouterr().err
