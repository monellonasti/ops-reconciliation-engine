"""Streamlit front end for the Ops Reconciliation Engine.

Run with ``streamlit run app.py``. All processing happens in memory; nothing
uploaded is written to disk. The only thing persisted is the review decision an
operator explicitly saves, in the SQLite file configured under ``history``.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import pandas as pd
import streamlit as st

from src.config import DEFAULT_RULES_PATH, REPO_ROOT, Rules, RulesConfigError, load_rules
from src.engine import apply_history, run_reconciliation
from src.explain import Explanation, explain_issue, explain_with_llm, llm_available
from src.history import ReviewHistory, fingerprint, open_history
from src.loader import DatasetLoadError, LoadedDataset, load_dataset
from src.models import (
    EXPECTED_COLUMNS,
    KEY_FIELD,
    SOURCE_ROW,
    Category,
    Issue,
    ReconciliationResult,
    ReviewStatus,
    Severity,
)
from src.reporting import full_report_csv, review_queue_csv
from src.utils import display_value, format_percentage, format_value, is_missing, normalize_iban

logger = logging.getLogger("ops_reconciliation.app")

DEMO_PREVIOUS = REPO_ROOT / "data" / "demo_previous.csv"
DEMO_CURRENT = REPO_ROOT / "data" / "demo_current.csv"

SEVERITY_LABEL = {
    Severity.CRITICAL: "🔴 Critical",
    Severity.WARNING: "🟠 Warning",
    Severity.INFO: "🔵 Info",
}
REVIEW_FILTER = ("All issues", "Review required", "No review needed")


def main() -> None:
    st.set_page_config(page_title="Ops Reconciliation Engine", layout="wide")
    st.title("Ops Reconciliation Engine")
    st.caption("Automate deterministic checks. Surface exceptions. Keep humans in control.")

    rules = load_rules_or_stop()
    history = open_history(rules)
    if st.session_state.get("result") is not None and st.session_state.get("run_rules") != rules:
        for key in ("result", "previous", "current", "sources", "run_rules", "ai_explanations"):
            st.session_state.pop(key, None)
        st.info("Rules changed. Run reconciliation again to apply them.")
    render_sidebar(rules, history)
    render_inputs(rules, history)

    if st.session_state.get("error"):
        st.error(st.session_state["error"])

    result: ReconciliationResult | None = st.session_state.get("result")
    if result is None:
        st.info("Upload the previous and current cycle exports, or load the demo dataset, to start.")
        return

    previous_label, current_label = st.session_state["sources"]
    if (previous_label, current_label) == (DEMO_PREVIOUS.name, DEMO_CURRENT.name):
        st.caption("Synthetic demo data. No real people or bank accounts are represented.")
    st.markdown(f"**Comparing** `{previous_label}` (previous) **with** `{current_label}` (current)")
    for note in result.notes:
        st.caption(f"Note: {note}")

    render_summary(result)
    selected = render_review_table(result)
    render_detail_panel(selected, rules, history)
    render_exports(result)


# --- setup -----------------------------------------------------------------------------


def load_rules_or_stop() -> Rules:
    try:
        return load_rules()
    except RulesConfigError as exc:
        st.error(f"The rules file could not be loaded: {exc}")
        st.stop()


def render_sidebar(rules: Rules, history: ReviewHistory | None) -> None:
    with st.sidebar:
        st.subheader("Rules in effect")
        st.caption(f"Loaded from `{DEFAULT_RULES_PATH.relative_to(REPO_ROOT).as_posix()}`")
        thresholds = pd.DataFrame(
            [
                ("Salary change: warning above", f"{rules.salary_change.warning_percentage:g}%"),
                ("Salary change: critical above", f"{rules.salary_change.critical_percentage:g}%"),
                ("Bonus: warning above", f"{rules.bonus.warning_salary_ratio:.0%} of salary"),
                ("Bonus: critical above", f"{rules.bonus.critical_salary_ratio:.0%} of salary"),
                ("Overtime: warning above", f"{rules.overtime.warning_hours:g} h"),
                ("Overtime: critical above", f"{rules.overtime.critical_hours:g} h"),
                ("IBAN change", rules.iban_change.severity.value),
                ("Duplicate employee_id", rules.duplicates.employee_id.value),
            ],
            columns=["Rule", "Value"],
        )
        st.dataframe(thresholds, hide_index=True, width="stretch")
        st.caption("Required fields: " + ", ".join(rules.required_fields))
        st.caption("Masked in the UI and exports: " + ", ".join(rules.masked_fields))

        st.subheader("Review history")
        if history is None:
            st.caption("Disabled in the rules file. Decisions are not stored between runs.")
        else:
            st.caption(
                f"Decisions are saved to `{history_display_path(history)}` "
                f"({history.count()} stored). A finding keeps its decision when it comes back "
                "in a later cycle with the same values."
            )

        st.subheader("Privacy")
        st.caption(
            "Files are processed in memory for this session only. Nothing is stored on disk "
            "except the review decisions you save, and no external service is called unless "
            "you explicitly request an AI explanation."
        )

        if st.button("Reset session", width="stretch"):
            for key in ("result", "previous", "current", "sources", "error", "ai_explanations", "run_rules", "upload_previous", "upload_current"):
                st.session_state.pop(key, None)
            st.query_params.pop("demo", None)
            st.rerun()


# --- inputs ------------------------------------------------------------------------------


def render_inputs(rules: Rules, history: ReviewHistory | None) -> None:
    st.subheader("1. Choose the two cycles")
    left, right = st.columns(2)
    previous_file = left.file_uploader("Previous cycle (CSV)", type=["csv"], key="upload_previous")
    current_file = right.file_uploader("Current cycle (CSV)", type=["csv"], key="upload_current")

    run_col, demo_col, _ = st.columns([1, 1, 3])
    run_clicked = run_col.button(
        "Run reconciliation",
        type="primary",
        disabled=previous_file is None or current_file is None,
        width="stretch",
    )
    demo_clicked = demo_col.button("Load demo dataset", width="stretch")

    # Opening the app with ?demo=1 loads the demo straight away (handy for sharing a link).
    auto_demo = "demo" in st.query_params and "result" not in st.session_state

    if run_clicked and previous_file is not None and current_file is not None:
        run_pipeline(
            previous_file, current_file, previous_file.name, current_file.name, rules, history
        )
    elif demo_clicked or auto_demo:
        run_pipeline(DEMO_PREVIOUS, DEMO_CURRENT, DEMO_PREVIOUS.name, DEMO_CURRENT.name, rules, history)


def run_pipeline(
    previous_source: Any,
    current_source: Any,
    previous_label: str,
    current_label: str,
    rules: Rules,
    history: ReviewHistory | None = None,
) -> None:
    st.session_state.pop("error", None)
    st.session_state.pop("ai_explanations", None)
    for key in ("result", "previous", "current", "sources", "run_rules"):
        st.session_state.pop(key, None)
    try:
        previous = load_dataset(previous_source, name="previous", rules=rules)
    except DatasetLoadError as exc:
        st.session_state["error"] = f"Previous cycle ({previous_label}): {exc}"
        return
    try:
        current = load_dataset(current_source, name="current", rules=rules)
    except DatasetLoadError as exc:
        st.session_state["error"] = f"Current cycle ({current_label}): {exc}"
        return
    try:
        result = run_reconciliation(previous, current, rules, history)
    except Exception:
        logger.error("Unexpected error during reconciliation; input values omitted")
        st.session_state["error"] = (
            "Something went wrong while reconciling the files. Check that both files are valid "
            "CSV exports with the expected columns, then try again."
        )
        return

    st.session_state.update(
        result=result,
        previous=previous,
        current=current,
        sources=(previous_label, current_label),
        run_rules=rules.model_copy(deep=True),
    )


# --- results -----------------------------------------------------------------------------


def render_summary(result: ReconciliationResult) -> None:
    st.subheader("2. Summary")
    summary = result.summary
    cards = [
        ("Records processed", summary.current_records, f"{summary.previous_records} in previous cycle"),
        ("New records", summary.new_records, None),
        ("Removed records", summary.removed_records, None),
        ("Critical issues", summary.critical_issues, None),
        ("Warnings", summary.warnings, None),
        ("Changes detected", summary.changes_detected, None),
        ("Records requiring review", summary.records_requiring_review, None),
    ]
    for column, (label, value, help_text) in zip(st.columns(len(cards)), cards, strict=True):
        column.metric(label, value, help=help_text)
    decided = summary.accepted_findings + summary.needs_action_findings
    if decided:
        st.caption(
            f"{decided} findings already carry a decision from an earlier run: "
            f"{summary.accepted_findings} accepted (excluded from the review count) and "
            f"{summary.needs_action_findings} marked as needing action."
        )


def render_review_table(result: ReconciliationResult) -> Issue | None:
    st.subheader("3. Review queue")
    filter_cols = st.columns([2, 3, 2, 2, 2])
    severities = filter_cols[0].multiselect(
        "Severity",
        options=list(Severity),
        default=list(Severity),
        format_func=lambda s: s.value.capitalize(),
    )
    categories = filter_cols[1].multiselect(
        "Category",
        options=list(Category),
        default=list(Category),
        format_func=lambda c: c.label,
    )
    review_choice = filter_cols[2].selectbox("Review required", REVIEW_FILTER, index=0)
    # Accepted findings are hidden by default: they are the work already done.
    statuses = filter_cols[3].multiselect(
        "Review status",
        options=list(ReviewStatus),
        default=[ReviewStatus.OPEN, ReviewStatus.NEEDS_ACTION],
        format_func=lambda s: s.label,
    )
    search = filter_cols[4].text_input("Employee ID contains", value="").strip().upper()

    filtered = [
        issue
        for issue in result.issues
        if issue.severity in severities
        and issue.category in categories
        and (
            review_choice == REVIEW_FILTER[0]
            or (review_choice == REVIEW_FILTER[1] and issue.requires_review)
            or (review_choice == REVIEW_FILTER[2] and not issue.requires_review)
        )
        and issue.review_status in statuses
        and (not search or search in issue.record_label.upper())
    ]

    st.caption(
        f"{len(filtered)} of {len(result.issues)} issues shown. "
        "Tick the box at the left of a row to see its details."
    )
    if not filtered:
        if not result.issues:
            st.success("No findings detected by the configured checks.")
        else:
            st.info("No findings match these filters.")
        return None

    table = issues_table(filtered)
    # The widget key follows the visible rows, so a selection never silently points at a
    # different finding after a filter change or a saved decision removes a row.
    rows_signature = hashlib.sha1("".join(fingerprint(issue) for issue in filtered).encode()).hexdigest()
    event = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=min(560, 38 * (len(table) + 1)),
        on_select="rerun",
        selection_mode="single-row",
        key=f"review_table_{rows_signature[:12]}",
        column_config={
            "Explanation": st.column_config.TextColumn(width="large"),
            "Field": st.column_config.TextColumn(width="small"),
            "Change": st.column_config.TextColumn(width="small"),
        },
    )
    rows = event.selection.rows if event and event.selection else []
    if rows and 0 <= rows[0] < len(filtered):
        return filtered[rows[0]]
    return None


def issues_table(issues: list[Issue]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Employee ID": [issue.record_label for issue in issues],
            "Cycle": [issue.dataset for issue in issues],
            # Nullable integers render as blanks and keep the column numeric for Arrow.
            "Source row": pd.array([issue.row_number for issue in issues], dtype="Int64"),
            "Category": [issue.category.label for issue in issues],
            "Field": [issue.field or "" for issue in issues],
            "Previous": [format_value(issue.previous_value) for issue in issues],
            "Current": [format_value(issue.current_value) for issue in issues],
            "Change": [format_percentage(issue.change_percentage) for issue in issues],
            "Severity": [SEVERITY_LABEL[issue.severity] for issue in issues],
            "Review Required": ["Yes" if issue.requires_review else "No" for issue in issues],
            "Status": [issue.review_status.label for issue in issues],
            "Explanation": [issue.message for issue in issues],
        }
    )


def render_detail_panel(issue: Issue | None, rules: Rules, history: ReviewHistory | None) -> None:
    st.subheader("4. Issue detail")
    if issue is None:
        st.caption(
            "Tick a row in the review queue to see what changed, why it was flagged and what to check."
        )
        return

    explanation = explain_issue(issue, rules)
    with st.container(border=True):
        st.markdown(
            f"**{issue.record_label}** · {issue.category.label} · {SEVERITY_LABEL[issue.severity]} · "
            f"Review required: **{'Yes' if issue.requires_review else 'No'}**"
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**What changed**")
            st.write(explanation.what_changed)
            st.markdown("**Why it was flagged**")
            st.write(explanation.why_flagged)
            st.markdown("**Rule triggered**")
            st.code(explanation.rule_triggered, language=None)
        with right:
            st.markdown("**Suggested operator action**")
            for action in explanation.suggested_actions:
                st.markdown(f"- {action}")
            st.caption(
                "The engine detects; it does not decide. Confirm the change with the source of truth "
                "before acting on it."
            )

        snapshot = record_snapshot(issue, rules)
        if snapshot is not None:
            with st.expander("Record snapshot (both cycles)"):
                st.dataframe(snapshot, hide_index=True, width="stretch")

        render_review_decision(issue, history)
        render_ai_explanation(issue, rules, explanation)


def record_snapshot(issue: Issue, rules: Rules) -> pd.DataFrame | None:
    """Side-by-side values of the record in both cycles, masked like everything else."""
    previous: LoadedDataset | None = st.session_state.get("previous")
    current: LoadedDataset | None = st.session_state.get("current")
    if previous is None or current is None:
        return None

    def find(dataset: LoadedDataset, wanted_dataset: str) -> dict[str, Any] | None:
        frame = dataset.frame
        if issue.employee_id:
            matches = frame[frame[KEY_FIELD] == issue.employee_id]
        elif issue.row_number is not None and issue.dataset == wanted_dataset:
            matches = frame[frame[SOURCE_ROW] == issue.row_number]
        else:
            return None
        return matches.iloc[0].to_dict() if len(matches) else None

    before = find(previous, "previous")
    after = find(current, "current")
    if before is None and after is None:
        return None

    rows = []
    for column in EXPECTED_COLUMNS:
        prev_value = display_value(column, before.get(column) if before else None, rules.masked_fields)
        curr_value = display_value(column, after.get(column) if after else None, rules.masked_fields)
        raw_prev = before.get(column) if before else None
        raw_curr = after.get(column) if after else None
        if column == "iban":
            raw_prev, raw_curr = normalize_iban(raw_prev), normalize_iban(raw_curr)
        unavailable = column in previous.missing_columns | current.missing_columns
        same = (is_missing(raw_prev) and is_missing(raw_curr)) or raw_prev == raw_curr
        rows.append(
            {
                "Field": column,
                "Previous": format_value(prev_value),
                "Current": format_value(curr_value),
                "Changed": "not compared" if unavailable else ("" if same else "yes"),
            }
        )
    if issue.employee_id:
        for dataset in (previous, current):
            candidates = dataset.frame[dataset.frame[KEY_FIELD] == issue.employee_id]
            if len(candidates) > 1:
                # No single candidate is authoritative; expose each for human inspection.
                return pd.DataFrame([
                    {"Cycle": source.name, "Source row": record[SOURCE_ROW],
                     **{field: display_value(field, record.get(field), rules.masked_fields)
                        for field in EXPECTED_COLUMNS}}
                    for source in (previous, current)
                    for record in source.frame[source.frame[KEY_FIELD] == issue.employee_id].to_dict("records")
                ])
    return pd.DataFrame(rows)


def render_ai_explanation(issue: Issue, rules: Rules, explanation: Explanation) -> None:
    st.markdown("**Optional: explain with AI**")
    if not llm_available():
        st.caption(
            "Not configured. Set `ANTHROPIC_API_KEY` and install the `anthropic` package to enable "
            "a natural-language rewrite of this finding. The application does not need it."
        )
        return

    cache: dict[str, str] = st.session_state.setdefault("ai_explanations", {})
    cache_key = issue.model_dump_json()
    if st.button("Explain this finding", key="ai_button"):
        with st.spinner("Asking the model to rephrase the finding..."):
            cache[cache_key] = explain_with_llm(issue, rules, explanation)
    if cache_key in cache:
        st.write(cache[cache_key])
        st.caption("Generated text. It rephrases the deterministic finding and does not judge whether the change is correct.")


def history_display_path(history: ReviewHistory) -> str:
    try:
        return history.path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(history.path)


def render_review_decision(issue: Issue, history: ReviewHistory | None) -> None:
    """Let the operator record what they decided; the engine never does this itself."""
    st.markdown("**Review decision**")
    if history is None:
        st.caption("Review history is disabled in the rules file, so decisions are not stored.")
        return

    if issue.review_status is not ReviewStatus.OPEN:
        who = f" by {issue.reviewed_by}" if issue.reviewed_by else ""
        note = f" Note: {issue.review_note}" if issue.review_note else ""
        st.caption(f"Current decision: {issue.review_status.label}{who} on {issue.reviewed_at}.{note}")

    key = fingerprint(issue)[:12]  # widgets reset when a different finding is selected
    status_col, note_col, reviewer_col = st.columns([2, 4, 2])
    status = status_col.selectbox(
        "Status",
        options=list(ReviewStatus),
        index=list(ReviewStatus).index(issue.review_status),
        format_func=lambda s: s.label,
        key=f"status_{key}",
    )
    note = note_col.text_input("Note (optional)", value=issue.review_note or "", key=f"note_{key}")
    reviewer = reviewer_col.text_input("Reviewer (optional)", key="reviewer")
    if st.button("Save decision", key=f"save_{key}"):
        save_decision(issue, history, status, note, reviewer)
        st.rerun()
    st.caption(
        "Accepted: verified, leaves the open queue and stays accepted if the same finding returns "
        "with the same values. Needs action: known problem, stays in the queue until corrected. "
        "Open: no decision yet."
    )


def save_decision(
    issue: Issue, history: ReviewHistory, status: ReviewStatus, note: str, reviewer: str
) -> None:
    """Persist one decision and refresh the result so the table and summary reflect it."""
    history.record(issue, status, note=note, reviewer=reviewer)
    result: ReconciliationResult | None = st.session_state.get("result")
    if result is not None:
        st.session_state["result"] = apply_history(result, history)


def render_exports(result: ReconciliationResult) -> None:
    st.subheader("5. Export")
    left, right, _ = st.columns([1, 1, 3])
    left.download_button(
        "Download Full Report",
        data=full_report_csv(result),
        file_name="reconciliation_report.csv",
        mime="text/csv",
        width="stretch",
    )
    right.download_button(
        "Download Review Queue",
        data=review_queue_csv(result),
        file_name="review_required.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(
        f"Full report: {len(result.issues)} issues with their review status. "
        f"Review queue: {len(result.review_queue)} issues flagged for a human decision and not "
        "yet accepted."
    )


if __name__ == "__main__":  # Streamlit runs the script as __main__
    main()
