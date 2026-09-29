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
from src import history as history_module
from src.config import REPO_ROOT
from src.history import ReviewHistory
from src.models import Category, Issue, ReviewStatus, Severity

APP_PATH = str(REPO_ROOT / "app.py")
FULL_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{20,}\b")


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch) -> ReviewHistory:
    """Keep UI tests away from the operator's real decision file."""
    history = ReviewHistory(tmp_path / "history.sqlite")
    monkeypatch.setattr(history_module, "open_history", lambda rules: history)
    return history


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
        "Severity", "Review Required", "Status", "Expected", "Explanation",
    ]
    assert len(review_table) == 47  # 46 findings plus one approved change that did not happen
    assert any(cell.startswith("matches:") for cell in review_table["Expected"])
    assert "not applied" in set(review_table["Expected"])
    assert set(review_table["Status"]) == {"Open"}  # isolated history: no decisions stored
    assert "" in set(review_table["Source row"]) and "175" in set(review_table["Source row"])
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


def test_demo_link_loads_once_per_session(monkeypatch):
    """After the link has done its job, a cleared result (failed run, changed rules) must
    stay cleared with its message instead of silently turning back into the demo."""
    from src import config

    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.query_params["demo"] = "1"
    at.run()
    assert at.metric
    monkeypatch.setattr(config, "load_rules", lambda: config.Rules(
        salary_change={"warning_percentage": 5, "critical_percentage": 10}
    ))
    at.run()
    assert any("Rules changed" in info.value for info in at.info)

    at.run()  # any later interaction

    assert not at.exception and at.metric == []


def test_unusable_history_file_does_not_stop_the_tool(isolated_history):
    isolated_history.path.write_bytes(b"not a database" * 100)

    at = click_button(run_app(), "Load demo dataset")

    assert not at.exception
    assert any("could not be read or written" in warning.value for warning in at.warning)
    metrics = {metric.label: str(metric.value) for metric in at.metric}
    assert metrics["Records processed"] == "203"


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


def test_unexpected_error_while_reading_a_file_is_a_plain_message(fake_session_state, rules, monkeypatch, caplog):
    """Library errors can quote the offending cell; neither the page nor the log may show it."""
    def explode(*_args, **_kwargs):
        raise ValueError("invalid literal for int(): 'IT60X0542811101000000123456'")

    monkeypatch.setattr(app_module, "load_dataset", explode)

    app_module.run_pipeline(b"x", b"x", "prev.csv", "curr.csv", rules)

    assert "Something went wrong" in fake_session_state["error"]
    assert "0542811101000000123456" not in fake_session_state["error"] + caplog.text
    assert "result" not in fake_session_state


def test_decisions_saved_in_another_session_reach_this_one(fake_session_state, isolated_history, rules):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules, isolated_history)
    issue = next(i for i in fake_session_state["result"].issues if i.employee_id == "EMP-00125")
    app_module.sync_decisions(isolated_history)  # nothing new: the result is kept as is
    unchanged = fake_session_state["result"]

    ReviewHistory(isolated_history.path).record(issue, ReviewStatus.ACCEPTED, reviewer="Colleague")
    app_module.sync_decisions(isolated_history)

    assert fake_session_state["result"] is not unchanged
    updated = next(i for i in fake_session_state["result"].issues if i.employee_id == "EMP-00125")
    assert updated.review_status is ReviewStatus.ACCEPTED and updated.reviewed_by == "Colleague"


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
        "Source row": "",  # cross-cycle finding: no single source line
        "Category": "Salary change",
        "Field": "monthly_salary",
        "Previous": "2,100",
        "Current": "3,000",
        "Change": "+42.86%",
        "Severity": "🔴 Critical",
        "Review Required": "Yes",
        "Status": "Open",
        "Expected": "",
        "Explanation": "Monthly salary increased by 42.86%.",
    }


# --- review decisions -----------------------------------------------------------------


def test_save_decision_persists_and_refreshes_the_result(fake_session_state, isolated_history, rules):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules, isolated_history)
    result = fake_session_state["result"]
    issue = next(i for i in result.issues if i.employee_id == "EMP-00125" and i.rule == "salary_change")
    before = result.summary.records_requiring_review

    app_module.save_decision(issue, isolated_history, ReviewStatus.ACCEPTED, "Promotion approved", "Ada")

    refreshed = fake_session_state["result"]
    updated = next(i for i in refreshed.issues if i.employee_id == "EMP-00125" and i.rule == "salary_change")
    assert updated.review_status is ReviewStatus.ACCEPTED
    assert updated.review_note == "Promotion approved"
    assert updated.reviewed_by == "Ada"
    assert refreshed.summary.accepted_findings == 1
    assert refreshed.summary.records_requiring_review == before - 1
    assert isolated_history.count() == 1

    app_module.save_decision(updated, isolated_history, ReviewStatus.OPEN, "", "")

    reopened = next(i for i in fake_session_state["result"].issues if i.employee_id == "EMP-00125" and i.rule == "salary_change")
    assert reopened.review_status is ReviewStatus.OPEN
    assert isolated_history.count() == 0


def test_demo_run_shows_decisions_from_an_earlier_run(isolated_history, rules):
    first = app_module.run_reconciliation(
        app_module.load_dataset(app_module.DEMO_PREVIOUS, name="previous", rules=rules),
        app_module.load_dataset(app_module.DEMO_CURRENT, name="current", rules=rules),
        rules,
    )
    accepted = next(i for i in first.issues if i.rule == "iban_change")
    isolated_history.record(accepted, ReviewStatus.ACCEPTED, note="Confirmed with the employee")

    at = click_button(run_app(), "Load demo dataset")

    assert not at.exception
    assert any("1 accepted" in caption.value for caption in at.caption)
    table = next(e.value for e in at.dataframe if "Employee ID" in e.value.columns)
    assert len(table) == 46  # the accepted finding is hidden by the default status filter
    assert "Accepted" not in set(table["Status"])


# --- language ----------------------------------------------------------------------------


def test_language_selector_switches_labels_and_messages_without_a_new_run():
    at = click_button(run_app(), "Load demo dataset")
    assert any(button.label == "Run reconciliation" for button in at.button)

    language = next(box for box in at.selectbox if box.label == "Language")
    language.set_value("it").run()

    assert not at.exception
    assert any(button.label == "Esegui riconciliazione" for button in at.button)
    assert any(button.label == "Carica dati demo" for button in at.button)
    metrics = {metric.label: str(metric.value) for metric in at.metric}
    assert metrics["Record elaborati"] == "203"
    table = next(e.value for e in at.dataframe if "ID dipendente" in e.value.columns)
    assert len(table) == 47
    assert "🔴 Critico" in set(table["Severità"])
    assert any("Retribuzione mensile aumentata" in text for text in table["Spiegazione"])
    assert not any("Monthly salary" in text for text in table["Spiegazione"])
    assert not any(info.value.startswith("Rules changed") for info in at.info)

    language = next(box for box in at.selectbox if box.label == "Lingua")
    language.set_value("en").run()
    assert not at.exception
    assert any(button.label == "Run reconciliation" for button in at.button)


def test_italian_rules_profile_drives_the_ui(monkeypatch):
    monkeypatch.setenv("OPS_RECON_RULES", "rules/validation_rules.it.yaml")

    at = click_button(run_app(), "Carica dati demo")

    assert not at.exception
    assert any("Confronto tra" in md.value for md in at.markdown)
    table = next(e.value for e in at.dataframe if "ID dipendente" in e.value.columns)
    assert any(cell.startswith("corrisponde:") for cell in table["Attesa"])
    assert any("/" in cell for cell in table["Corrente"] if cell)  # dates shown as GG/MM/AAAA


def test_exports_are_built_once_per_result(fake_session_state, isolated_history, rules, monkeypatch):
    app_module.run_pipeline(app_module.DEMO_PREVIOUS, app_module.DEMO_CURRENT, "p", "c", rules, isolated_history)
    result = fake_session_state["result"]
    builds = []
    real = app_module.full_report_csv
    monkeypatch.setattr(app_module, "full_report_csv", lambda r: builds.append(r) or real(r))

    first = app_module.export_files(result)
    again = app_module.export_files(result)  # a click in the table: same result
    issue = next(i for i in result.issues if i.employee_id == "EMP-00125")
    app_module.save_decision(issue, isolated_history, ReviewStatus.ACCEPTED, "", "")
    updated = app_module.export_files(fake_session_state["result"])

    assert first == again and len(builds) == 2
    assert b"accepted" in updated[0] and b"accepted" not in first[0]
