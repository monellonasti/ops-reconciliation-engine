"""Review history: decisions persist, follow a finding across runs, and never leak values."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src.config import REPO_ROOT, Rules, rules_from_dict
from src.engine import apply_history, main, reconcile_sources
from src.history import ReviewHistory, fingerprint, open_history
from src.models import ReviewStatus
from src.reporting import full_report_csv, review_queue_csv
from tests.conftest import csv_bytes, employee


@pytest.fixture
def history(tmp_path) -> ReviewHistory:
    return ReviewHistory(tmp_path / "decisions" / "history.sqlite")


def salary_run(history: ReviewHistory | None = None, current: str = "3000"):
    return reconcile_sources(
        csv_bytes([employee(monthly_salary="2100")]),
        csv_bytes([employee(monthly_salary=current)]),
        Rules(),
        history,
    )


def salary_issue(result):
    return next(issue for issue in result.issues if issue.rule == "salary_change")


# --- identity ----------------------------------------------------------------------


def test_fingerprint_follows_the_values_shown_not_the_wording():
    first = salary_issue(salary_run())
    same = salary_issue(salary_run())
    reworded = first.model_copy(update={"message": "different wording"})
    other_value = salary_issue(salary_run(current="3200"))

    assert fingerprint(first) == fingerprint(same) == fingerprint(reworded)
    assert fingerprint(first) != fingerprint(other_value)


# --- storage -----------------------------------------------------------------------


def test_nothing_is_written_until_a_decision_is_saved(history):
    result = salary_run(history)

    assert not history.path.exists()
    assert history.count() == 0
    assert salary_issue(result).review_status is ReviewStatus.OPEN

    history.record(salary_issue(result), ReviewStatus.ACCEPTED, note="Promotion", reviewer="Ada")

    assert history.path.exists()
    assert history.count() == 1


def test_decision_is_attached_on_the_next_run(history):
    history.record(salary_issue(salary_run()), ReviewStatus.ACCEPTED, note="Promotion", reviewer="Ada")

    result = salary_run(history)
    issue = salary_issue(result)

    assert issue.review_status is ReviewStatus.ACCEPTED
    assert issue.review_note == "Promotion"
    assert issue.reviewed_by == "Ada"
    assert issue.reviewed_at  # ISO timestamp
    assert issue.requires_review is True  # the rule still flags it; the human accepted it
    assert result.review_queue == []
    assert result.summary.records_requiring_review == 0
    assert result.summary.accepted_findings == 1
    assert result.summary.needs_action_findings == 0


def test_a_different_value_reopens_the_finding(history):
    history.record(salary_issue(salary_run()), ReviewStatus.ACCEPTED)

    result = salary_run(history, current="3200")

    assert salary_issue(result).review_status is ReviewStatus.OPEN
    assert result.summary.records_requiring_review == 1


def test_needs_action_stays_in_the_queue(history):
    history.record(salary_issue(salary_run()), ReviewStatus.NEEDS_ACTION, note="Ask HR")

    result = salary_run(history)

    assert salary_issue(result).review_status is ReviewStatus.NEEDS_ACTION
    assert len(result.review_queue) == 1
    assert result.summary.records_requiring_review == 1
    assert result.summary.needs_action_findings == 1


def test_recording_open_clears_the_decision_and_logs_both_steps(history):
    issue = salary_issue(salary_run())
    history.record(issue, ReviewStatus.ACCEPTED, reviewer="Ada")
    history.record(issue, ReviewStatus.OPEN, reviewer="Bea")

    assert history.count() == 0
    assert salary_issue(salary_run(history)).review_status is ReviewStatus.OPEN
    with sqlite3.connect(history.path) as connection:
        log = connection.execute("SELECT action, status, reviewer FROM decision_log ORDER BY id").fetchall()
    assert log == [("set", "accepted", "Ada"), ("clear", "open", "Bea")]


def test_replacing_a_decision_keeps_one_row(history):
    issue = salary_issue(salary_run())
    history.record(issue, ReviewStatus.NEEDS_ACTION, note="first")
    history.record(issue, ReviewStatus.ACCEPTED, note="second")

    assert history.count() == 1
    assert salary_issue(salary_run(history)).review_note == "second"


def test_clearing_an_unknown_finding_is_harmless(history):
    history.clear(salary_issue(salary_run()))

    assert not history.path.exists()


def test_notes_are_trimmed_and_redacted(history):
    issue = salary_issue(salary_run())
    history.record(issue, ReviewStatus.ACCEPTED, note="  paid to IT60X0542811101000000123456  ", reviewer="  ")

    stored = salary_issue(salary_run(history))
    assert stored.review_note == "paid to IT60X****3456"
    assert stored.reviewed_by is None


def test_apply_history_refreshes_an_existing_result(history):
    result = salary_run(history)
    history.record(salary_issue(result), ReviewStatus.ACCEPTED)

    refreshed = apply_history(result, history)

    assert salary_issue(result).review_status is ReviewStatus.OPEN  # original untouched
    assert salary_issue(refreshed).review_status is ReviewStatus.ACCEPTED
    assert refreshed.summary.records_requiring_review == 0
    assert refreshed.summary.current_records == result.summary.current_records


def test_lookup_handles_many_findings(history):
    rows = [employee(employee_id=f"EMP-{i:05d}", email=f"e{i}@example.com", iban="") for i in range(1200)]
    changed = [dict(row, monthly_salary="3000") for row in rows]
    first = reconcile_sources(csv_bytes(rows), csv_bytes(changed), Rules())
    history.record(first.issues[0], ReviewStatus.ACCEPTED)
    history.record(first.issues[-1], ReviewStatus.NEEDS_ACTION)

    second = reconcile_sources(csv_bytes(rows), csv_bytes(changed), Rules(), history)

    assert len(second.issues) == 1200
    assert second.summary.accepted_findings == 1
    assert second.summary.needs_action_findings == 1


# --- exports and configuration ---------------------------------------------------------


def test_exports_carry_the_review_state(history):
    history.record(salary_issue(salary_run()), ReviewStatus.ACCEPTED, note="Promotion", reviewer="Ada")
    result = salary_run(history)

    full = pd.read_csv(pd.io.common.BytesIO(full_report_csv(result)))
    queue = pd.read_csv(pd.io.common.BytesIO(review_queue_csv(result)))

    assert {"review_status", "review_note", "reviewed_by", "reviewed_at"} <= set(full.columns)
    assert full.loc[0, "review_status"] == "accepted"
    assert full.loc[0, "review_note"] == "Promotion"
    assert queue.empty


def test_history_can_be_disabled_and_paths_resolve_from_the_repo_root():
    assert open_history(rules_from_dict({"history": {"enabled": False}})) is None

    default = open_history(Rules())
    assert default is not None
    assert default.path == REPO_ROOT / "history" / "review_history.sqlite"
    assert open_history(rules_from_dict({"history": {"path": "C:/elsewhere/h.sqlite"}})).path.is_absolute()


def test_cli_reports_stored_decisions(tmp_path, capsys):
    previous, current = tmp_path / "previous.csv", tmp_path / "current.csv"
    previous.write_bytes(csv_bytes([employee(monthly_salary="2100")]))
    current.write_bytes(csv_bytes([employee(monthly_salary="3000")]))
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(f"history:\n  path: {(tmp_path / 'h.sqlite').as_posix()}\n", encoding="utf-8")
    history = ReviewHistory(tmp_path / "h.sqlite")
    history.record(salary_issue(salary_run()), ReviewStatus.ACCEPTED)

    exit_code = main([str(previous), str(current), "--rules", str(rules_file), "--output-dir", str(tmp_path / "out")])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Records requiring review: 0" in output
    assert "Findings with a stored decision: 1 (1 accepted, 0 need action)" in output


# --- unusable files ----------------------------------------------------------------


def row_level_run(history: ReviewHistory | None = None, rules: Rules | None = None):
    """A finding with no employee_id: identified by its source row."""
    return reconcile_sources(
        csv_bytes([employee()]),
        csv_bytes([employee(), employee(employee_id="", email="other@example.com", iban="")]),
        rules or Rules(),
        history,
    )


def test_row_level_decisions_survive_a_language_switch(history):
    row_finding = next(issue for issue in row_level_run().issues if issue.employee_id is None)
    history.record(row_finding, ReviewStatus.ACCEPTED)

    italian = rules_from_dict({"language": "it"})
    reopened = next(issue for issue in row_level_run(history, italian).issues if issue.employee_id is None)

    assert reopened.record_label.startswith("riga")
    assert reopened.review_status is ReviewStatus.ACCEPTED


def test_english_fingerprints_of_row_findings_are_unchanged():
    """Decisions saved before the fingerprint became language-neutral still match."""
    import hashlib
    import json

    finding = next(issue for issue in row_level_run().issues if issue.employee_id is None)
    legacy = [finding.record_label, finding.rule, finding.field, finding.previous_value, finding.current_value]

    assert fingerprint(finding) == hashlib.sha256(json.dumps(legacy, default=str).encode()).hexdigest()


@pytest.mark.parametrize("kind", ["not a database", "a folder"])
def test_unusable_history_file_raises_one_operator_error(tmp_path, kind):
    from src.history import HistoryError

    path = tmp_path / "history.sqlite"
    if kind == "a folder":
        path.mkdir()
    else:
        path.write_bytes(b"spreadsheet saved over the history file" * 50)
    history = ReviewHistory(path)
    finding = salary_issue(salary_run())

    for action in (history.count, lambda: history.apply([finding]), lambda: history.record(finding, ReviewStatus.ACCEPTED)):
        with pytest.raises(HistoryError, match="could not be read or written"):
            action()


def test_locked_history_asks_to_retry(history, monkeypatch):
    """Another operator saving at the same moment: a retry message, not a crash."""
    from src.history import HistoryError

    finding = salary_issue(salary_run())
    history.record(finding, ReviewStatus.ACCEPTED)
    blocker = sqlite3.connect(history.path)
    blocker.execute("BEGIN EXCLUSIVE")
    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda path: connect(path, timeout=0.05))
    try:
        with pytest.raises(HistoryError, match="busy"):
            history.record(finding, ReviewStatus.NEEDS_ACTION)
    finally:
        blocker.rollback()
        blocker.close()


def test_run_continues_without_decisions_when_the_history_is_unreadable(tmp_path):
    damaged = tmp_path / "history.sqlite"
    damaged.write_bytes(b"not a database" * 100)

    result = salary_run(ReviewHistory(damaged))

    assert salary_issue(result).review_status is ReviewStatus.OPEN
    assert any("could not be read or written" in note for note in result.notes)


def test_version_changes_when_a_decision_is_saved(history):
    assert history.version() is None
    finding = salary_issue(salary_run())

    history.record(finding, ReviewStatus.ACCEPTED)
    first = history.version()
    history.record(finding, ReviewStatus.NEEDS_ACTION, note="Payroll to correct")

    assert first is not None and history.version() != first
