"""Headless checks of the Streamlit front end via Streamlit's AppTest.

These cover the glue between UI and engine: the demo flow, error messages
and masking in what is rendered. The engine itself is tested elsewhere.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app as app_module
from src.config import REPO_ROOT
from src.models import Category, Issue, Severity

APP_PATH = str(REPO_ROOT / "app.py")
FULL_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{20,}\b")


def run_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=60).run()


def click_button(at: AppTest, label: str) -> AppTest:
    button = next(button for button in at.button if button.label == label)
    button.click()
    return at.run()


def test_start_screen_has_no_result_and_no_exception():
    at = run_app()

    assert not at.exception
    assert any("load the demo dataset" in info.value for info in at.info)
    assert at.metric == []


def test_demo_dataset_fills_summary_table_and_exports():
    at = click_button(run_app(), "Load demo dataset")

    assert not at.exception
    metrics = {metric.label: str(metric.value) for metric in at.metric}
    assert metrics["Records processed"] == "203"
    assert metrics["New records"] == "4"
    assert metrics["Removed records"] == "3"
    assert int(metrics["Critical issues"]) > 0
    assert int(metrics["Records requiring review"]) > 0

    review_table = next(
        element.value for element in at.dataframe if "Employee ID" in element.value.columns
    )
    assert list(review_table.columns) == [
        "Employee ID", "Cycle", "Source row", "Category", "Field", "Previous", "Current", "Change",
        "Severity", "Review Required", "Explanation",
    ]
    assert len(review_table) == 46
    assert set(review_table["Severity"]) == {"🔴 Critical", "🟠 Warning", "🔵 Info"}
    assert "Download Full Report" in [button.label for button in at.get("download_button")]
    assert "Download Review Queue" in [button.label for button in at.get("download_button")]


def test_rendered_tables_never_contain_a_full_iban():
    at = click_button(run_app(), "Load demo dataset")

    for element in at.dataframe:
        text = element.value.to_csv()
        assert not FULL_IBAN.search(text), "an unmasked IBAN reached the UI"
    assert any("****" in element.value.to_csv() for element in at.dataframe)


def test_reset_clears_the_result():
    at = click_button(run_app(), "Load demo dataset")
    assert at.metric

    at = click_button(at, "Reset session")

    assert not at.exception
    assert at.metric == []


def test_reset_from_demo_link_does_not_reload_demo():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["demo"] = "1"
    at.run()
    assert at.metric
    at = click_button(at, "Reset session")
    assert not at.exception and at.metric == []
    assert "demo" not in at.query_params


def test_filters_and_no_matches_state():
    at = click_button(run_app(), "Load demo dataset")
    at.multiselect[0].set_value([Severity.CRITICAL]).run()
    table = next(d.value for d in at.dataframe if "Employee ID" in d.value.columns)
    assert set(table.Severity) == {"🔴 Critical"}
    at.text_input[0].set_value("NO-SUCH-EMPLOYEE").run()
    assert any("No findings match" in info.value for info in at.info)
    assert not at.exception


def test_changed_rules_invalidate_existing_results(monkeypatch):
    from src import config
    at = click_button(run_app(), "Load demo dataset")
    monkeypatch.setattr(config, "load_rules", lambda: config.Rules(
        salary_change={"warning_percentage": 5, "critical_percentage": 10}
    ))
    at.run()
    assert not at.exception and not at.metric
    assert any("Rules changed" in info.value for info in at.info)


# --- glue functions -------------------------------------------------------------------


@pytest.fixture
def fake_session_state(monkeypatch):
    state: dict = {}
    monkeypatch.setattr(app_module.st, "session_state", state)
    return state


def test_run_pipeline_reports_unreadable_previous_file(fake_session_state, rules):
    app_module.run_pipeline(b"", b"employee_id\nEMP-1\n", "prev.csv", "curr.csv", rules)

    assert "Previous cycle (prev.csv)" in fake_session_state["error"]
    assert "empty" in fake_session_state["error"]
    assert "result" not in fake_session_state


def test_run_pipeline_reports_missing_columns_in_current_file(fake_session_state, rules):
    good = (REPO_ROOT / "data" / "demo_previous.csv").read_bytes()
    bad = b"employee_id,first_name\nEMP-1,Ada\n"

    app_module.run_pipeline(good, bad, "prev.csv", "curr.csv", rules)

    assert fake_session_state["error"].startswith("Current cycle (curr.csv)")
    assert "Missing required column" in fake_session_state["error"]


def test_run_pipeline_hides_unexpected_errors_behind_a_plain_message(fake_session_state, rules, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(app_module, "run_reconciliation", explode)
    good = (REPO_ROOT / "data" / "demo_previous.csv").read_bytes()

    app_module.run_pipeline(good, good, "prev.csv", "curr.csv", rules)

    assert "secret internal detail" not in fake_session_state["error"]
    assert "Something went wrong" in fake_session_state["error"]


def test_run_pipeline_stores_result_and_datasets(fake_session_state, rules):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules)

    assert "error" not in fake_session_state
    assert fake_session_state["result"].summary.current_records == 203
    assert fake_session_state["sources"] == ("p", "c")


def test_record_snapshot_masks_iban_and_marks_changes(fake_session_state, rules):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules)
    issue = next(
        i for i in fake_session_state["result"].issues
        if i.employee_id == "EMP-00023" and i.rule == "iban_change"
    )

    snapshot = app_module.record_snapshot(issue, rules)

    assert isinstance(snapshot, pd.DataFrame)
    iban_row = snapshot[snapshot["Field"] == "iban"].iloc[0]
    assert iban_row["Changed"] == "yes"
    assert "****" in iban_row["Previous"] and "****" in iban_row["Current"]
    assert not FULL_IBAN.search(snapshot.to_csv())
    assert snapshot[snapshot["Field"] == "first_name"].iloc[0]["Changed"] == ""


def test_record_snapshot_for_a_row_without_id_uses_the_row_number(fake_session_state, rules):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules)
    issue = next(
        i for i in fake_session_state["result"].issues
        if i.employee_id is None and i.rule == "missing_required_field"
    )

    snapshot = app_module.record_snapshot(issue, rules)

    assert snapshot is not None
    assert snapshot[snapshot["Field"] == "employee_id"].iloc[0]["Current"] == ""
    assert snapshot[snapshot["Field"] == "first_name"].iloc[0]["Current"] != ""


def test_issues_table_formats_values_for_operators():
    issue = Issue(
        employee_id="EMP-00125",
        dataset="both",
        category=Category.SALARY_CHANGE,
        field="monthly_salary",
        previous_value=2100.0,
        current_value=3000.0,
        change_percentage=42.86,
        rule="salary_change",
        severity=Severity.CRITICAL,
        requires_review=True,
        message="Monthly salary increased by 42.86%.",
    )

    table = app_module.issues_table([issue])

    assert table.iloc[0].to_dict() == {
        "Employee ID": "EMP-00125",
        "Cycle": "both",
        "Source row": "",
        "Category": "Salary change",
        "Field": "monthly_salary",
        "Previous": "2,100",
        "Current": "3,000",
        "Change": "+42.86%",
        "Severity": "🔴 Critical",
        "Review Required": "Yes",
        "Explanation": "Monthly salary increased by 42.86%.",
    }
