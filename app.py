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

from src.config import REPO_ROOT, Rules, RulesConfigError, default_rules_path, load_rules
from src.engine import apply_history, apply_presentation, run_reconciliation
from src.expectations import EXPECTABLE_FIELDS, ExpectedChanges, load_expected_changes
from src.explain import Explanation, explain_issue, explain_with_llm, llm_available
from src.history import ReviewHistory, fingerprint, open_history
from src.i18n import available_languages, t
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
from src.utils import (
    display_value,
    format_for_display,
    format_percentage,
    format_plain,
    format_timestamp,
    is_missing,
    normalize_iban,
)

logger = logging.getLogger("ops_reconciliation.app")

DEMO_PREVIOUS = REPO_ROOT / "data" / "demo_previous.csv"
DEMO_CURRENT = REPO_ROOT / "data" / "demo_current.csv"
DEMO_EXPECTED = REPO_ROOT / "data" / "demo_expected_changes.csv"
UPLOAD_TYPES = ["csv", "xlsx"]
LANGUAGE_NAMES = {"en": "English", "it": "Italiano"}
SEVERITY_MARK = {Severity.CRITICAL: "🔴", Severity.WARNING: "🟠", Severity.INFO: "🔵"}

RUN_STATE_KEYS = ("result", "previous", "current", "sources", "run_rules", "expected", "expected_obj")


def severity_label(severity: Severity) -> str:
    return f"{SEVERITY_MARK[severity]} {severity.label}"


def main() -> None:
    st.set_page_config(page_title="Ops Reconciliation Engine", layout="wide")
    rules = load_rules_or_stop()
    rules = with_session_language(rules)
    apply_presentation(rules)

    st.title("Ops Reconciliation Engine")
    st.caption(t("ui.subtitle"))

    history = open_history(rules)
    refresh_if_rules_changed(rules, history)
    render_sidebar(rules, history)
    render_inputs(rules, history)

    if st.session_state.get("error"):
        st.error(st.session_state["error"])

    result: ReconciliationResult | None = st.session_state.get("result")
    if result is None:
        st.info(t("ui.start_hint"))
        return

    previous_label, current_label = st.session_state["sources"]
    if (previous_label, current_label) == (DEMO_PREVIOUS.name, DEMO_CURRENT.name):
        st.caption(t("ui.demo_notice"))
    st.markdown(t("ui.comparing", previous=previous_label, current=current_label))
    expected_info = st.session_state.get("expected")
    if expected_info:
        st.caption(t("ui.expected_entries", count=expected_info[1], name=expected_info[0]))
    for note in result.notes:
        st.caption(t("ui.note", note=note))

    render_summary(result)
    selected = render_review_table(result)
    render_detail_panel(selected, rules, history)
    render_exports(result)


# --- setup -----------------------------------------------------------------------------


def load_rules_or_stop() -> Rules:
    try:
        return load_rules()
    except RulesConfigError as exc:
        st.error(t("ui.rules_error", error=exc))
        st.stop()


def with_session_language(rules: Rules) -> Rules:
    """The rules file sets the default language; the sidebar can override it for the session."""
    choice = st.session_state.get("language")
    if choice and choice != rules.language and choice in available_languages():
        return rules.model_copy(update={"language": choice})
    return rules


def refresh_if_rules_changed(rules: Rules, history: ReviewHistory | None) -> None:
    """A result computed under other rules is stale. A language-only change is re-run
    silently from the loaded files; any other change asks for a new run."""
    if st.session_state.get("result") is None or st.session_state.get("run_rules") == rules:
        return
    previous_rules: Rules = st.session_state["run_rules"]
    only_language = previous_rules.model_copy(update={"language": rules.language}) == rules
    if only_language and "previous" in st.session_state and "current" in st.session_state:
        result = run_reconciliation(
            st.session_state["previous"],
            st.session_state["current"],
            rules,
            history,
            st.session_state.get("expected_obj"),
        )
        st.session_state.update(result=result, run_rules=rules.model_copy(deep=True))
        st.session_state.pop("ai_explanations", None)
        return
    for key in (*RUN_STATE_KEYS, "ai_explanations"):
        st.session_state.pop(key, None)
    st.info(t("ui.rules_changed"))


def render_sidebar(rules: Rules, history: ReviewHistory | None) -> None:
    with st.sidebar:
        languages = available_languages()
        st.selectbox(
            t("ui.sidebar.language"),
            options=languages,
            index=languages.index(rules.language),
            format_func=lambda code: LANGUAGE_NAMES.get(code, code),
            key="language",
        )

        st.subheader(t("ui.sidebar.rules"))
        st.caption(t("ui.sidebar.loaded_from", path=rules_display_path()))
        thresholds = pd.DataFrame(
            [
                (t("ui.sidebar.salary_warning"), f"{format_plain(rules.salary_change.warning_percentage)}%"),
                (t("ui.sidebar.salary_critical"), f"{format_plain(rules.salary_change.critical_percentage)}%"),
                (t("ui.sidebar.bonus_warning"), t("ui.sidebar.of_salary", value=f"{rules.bonus.warning_salary_ratio:.0%}")),
                (t("ui.sidebar.bonus_critical"), t("ui.sidebar.of_salary", value=f"{rules.bonus.critical_salary_ratio:.0%}")),
                (t("ui.sidebar.overtime_warning"), f"{format_plain(rules.overtime.warning_hours)} h"),
                (t("ui.sidebar.overtime_critical"), f"{format_plain(rules.overtime.critical_hours)} h"),
                (t("ui.sidebar.iban_change"), rules.iban_change.severity.label),
                (t("ui.sidebar.duplicate_id"), rules.duplicates.employee_id.label),
            ],
            columns=[t("ui.sidebar.rule"), t("ui.sidebar.value")],
        )
        st.dataframe(thresholds, hide_index=True, width="stretch")
        st.caption(t("ui.sidebar.required_fields", fields=", ".join(rules.required_fields)))
        st.caption(t("ui.sidebar.masked_fields", fields=", ".join(rules.masked_fields)))
        st.caption(
            t(
                "ui.sidebar.formats",
                dates=" / ".join(rules.formats.input_date_formats),
                decimal=rules.formats.decimal_separator,
                thousands=rules.formats.thousands_separator,
            )
        )

        st.subheader(t("ui.sidebar.history"))
        if history is None:
            st.caption(t("ui.sidebar.history_disabled"))
        else:
            st.caption(
                t("ui.sidebar.history_enabled", path=history_display_path(history), count=history.count())
            )

        st.subheader(t("ui.sidebar.privacy"))
        st.caption(t("ui.sidebar.privacy_text"))

        if st.button(t("ui.sidebar.reset"), width="stretch"):
            for key in (
                *RUN_STATE_KEYS, "error", "ai_explanations",
                "upload_previous", "upload_current", "upload_expected",
            ):
                st.session_state.pop(key, None)
            st.query_params.pop("demo", None)
            st.rerun()


def rules_display_path() -> str:
    path = default_rules_path()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


# --- inputs ------------------------------------------------------------------------------


def render_inputs(rules: Rules, history: ReviewHistory | None) -> None:
    st.subheader(t("ui.inputs.title"))
    left, right = st.columns(2)
    previous_file = left.file_uploader(t("ui.inputs.previous"), type=UPLOAD_TYPES, key="upload_previous")
    current_file = right.file_uploader(t("ui.inputs.current"), type=UPLOAD_TYPES, key="upload_current")
    expected_file = st.file_uploader(
        t("ui.inputs.expected"),
        type=UPLOAD_TYPES,
        key="upload_expected",
        help=t("ui.inputs.expected_help", fields=", ".join(EXPECTABLE_FIELDS)),
    )

    run_col, demo_col, _ = st.columns([1, 1, 3])
    run_clicked = run_col.button(
        t("ui.inputs.run"),
        type="primary",
        disabled=previous_file is None or current_file is None,
        width="stretch",
    )
    demo_clicked = demo_col.button(t("ui.inputs.demo"), width="stretch")

    # Opening the app with ?demo=1 loads the demo straight away (handy for sharing a link).
    auto_demo = "demo" in st.query_params and "result" not in st.session_state

    if run_clicked and previous_file is not None and current_file is not None:
        run_pipeline(
            previous_file,
            current_file,
            previous_file.name,
            current_file.name,
            rules,
            history,
            expected_source=expected_file,
            expected_label=expected_file.name if expected_file is not None else None,
        )
    elif demo_clicked or auto_demo:
        run_pipeline(
            DEMO_PREVIOUS,
            DEMO_CURRENT,
            DEMO_PREVIOUS.name,
            DEMO_CURRENT.name,
            rules,
            history,
            expected_source=DEMO_EXPECTED,
            expected_label=DEMO_EXPECTED.name,
        )


def run_pipeline(
    previous_source: Any,
    current_source: Any,
    previous_label: str,
    current_label: str,
    rules: Rules,
    history: ReviewHistory | None = None,
    expected_source: Any | None = None,
    expected_label: str | None = None,
) -> None:
    st.session_state.pop("error", None)
    st.session_state.pop("ai_explanations", None)
    for key in RUN_STATE_KEYS:
        st.session_state.pop(key, None)
    apply_presentation(rules)
    try:
        previous = load_dataset(previous_source, name="previous", rules=rules)
    except DatasetLoadError as exc:
        st.session_state["error"] = t("ui.error.previous", name=previous_label, error=exc)
        return
    try:
        current = load_dataset(current_source, name="current", rules=rules)
    except DatasetLoadError as exc:
        st.session_state["error"] = t("ui.error.current", name=current_label, error=exc)
        return
    expected: ExpectedChanges | None = None
    if expected_source is not None:
        try:
            expected = load_expected_changes(expected_source)
        except DatasetLoadError as exc:
            st.session_state["error"] = t("ui.error.expected", name=expected_label, error=exc)
            return
    try:
        result = run_reconciliation(previous, current, rules, history, expected)
    except Exception:
        logger.error("Unexpected error during reconciliation; input values omitted")
        st.session_state["error"] = t("ui.error.unexpected")
        return

    st.session_state.update(
        result=result,
        previous=previous,
        current=current,
        sources=(previous_label, current_label),
        run_rules=rules.model_copy(deep=True),
        expected=(expected_label, len(expected)) if expected is not None else None,
        expected_obj=expected,
    )


# --- results -----------------------------------------------------------------------------


def render_summary(result: ReconciliationResult) -> None:
    st.subheader(t("ui.summary.title"))
    summary = result.summary
    cards = [
        (t("ui.summary.records"), summary.current_records, t("ui.summary.records_help", count=summary.previous_records)),
        (t("ui.summary.new"), summary.new_records, None),
        (t("ui.summary.removed"), summary.removed_records, None),
        (t("ui.summary.critical"), summary.critical_issues, None),
        (t("ui.summary.warnings"), summary.warnings, None),
        (t("ui.summary.changes"), summary.changes_detected, None),
        (t("ui.summary.review"), summary.records_requiring_review, None),
    ]
    for column, (label, value, help_text) in zip(st.columns(len(cards)), cards, strict=True):
        column.metric(label, value, help=help_text)
    decided = summary.accepted_findings + summary.needs_action_findings
    if decided:
        st.caption(
            t(
                "ui.summary.decided",
                decided=decided,
                accepted=summary.accepted_findings,
                needs_action=summary.needs_action_findings,
            )
        )


def render_review_table(result: ReconciliationResult) -> Issue | None:
    st.subheader(t("ui.queue.title"))
    filter_cols = st.columns([2, 3, 2, 2, 2])
    severities = filter_cols[0].multiselect(
        t("ui.queue.severity"),
        options=list(Severity),
        default=list(Severity),
        format_func=lambda s: s.label,
    )
    categories = filter_cols[1].multiselect(
        t("ui.queue.category"),
        options=list(Category),
        default=list(Category),
        format_func=lambda c: c.label,
    )
    review_options = (t("ui.queue.review_all"), t("ui.queue.review_yes"), t("ui.queue.review_no"))
    review_choice = filter_cols[2].selectbox(t("ui.queue.review_required"), review_options, index=0)
    # Accepted findings are hidden by default: they are the work already done.
    statuses = filter_cols[3].multiselect(
        t("ui.queue.status"),
        options=list(ReviewStatus),
        default=[ReviewStatus.OPEN, ReviewStatus.NEEDS_ACTION],
        format_func=lambda s: s.label,
    )
    search = filter_cols[4].text_input(t("ui.queue.search"), value="").strip().upper()

    filtered = [
        issue
        for issue in result.issues
        if issue.severity in severities
        and issue.category in categories
        and (
            review_choice == review_options[0]
            or (review_choice == review_options[1] and issue.requires_review)
            or (review_choice == review_options[2] and not issue.requires_review)
        )
        and issue.review_status in statuses
        and (not search or search in issue.record_label.upper())
    ]

    st.caption(t("ui.queue.shown", shown=len(filtered), total=len(result.issues)))
    if not filtered:
        if not result.issues:
            st.success(t("ui.queue.none"))
        else:
            st.info(t("ui.queue.no_match"))
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
            t("ui.column.explanation"): st.column_config.TextColumn(width="large"),
            t("ui.column.field"): st.column_config.TextColumn(width="small"),
            t("ui.column.change"): st.column_config.TextColumn(width="small"),
        },
    )
    rows = event.selection.rows if event and event.selection else []
    if rows and 0 <= rows[0] < len(filtered):
        return filtered[rows[0]]
    return None


def issues_table(issues: list[Issue]) -> pd.DataFrame:
    yes, no = t("ui.yes"), t("ui.no")
    return pd.DataFrame(
        {
            t("ui.column.employee"): [issue.record_label for issue in issues],
            t("ui.column.cycle"): [t(f"dataset.{issue.dataset}") for issue in issues],
            # Text on purpose: a mixed int/blank column breaks Arrow and nullable ints show "None".
            t("ui.column.source_row"): ["" if issue.row_number is None else str(issue.row_number) for issue in issues],
            t("ui.column.category"): [issue.category.label for issue in issues],
            t("ui.column.field"): [issue.field or "" for issue in issues],
            t("ui.column.previous"): [format_for_display(issue.previous_value) for issue in issues],
            t("ui.column.current"): [format_for_display(issue.current_value) for issue in issues],
            t("ui.column.change"): [format_percentage(issue.change_percentage) for issue in issues],
            t("ui.column.severity"): [severity_label(issue.severity) for issue in issues],
            t("ui.column.review_required"): [yes if issue.requires_review else no for issue in issues],
            t("ui.column.status"): [issue.review_status.label for issue in issues],
            t("ui.column.expected"): [expected_label(issue) for issue in issues],
            t("ui.column.explanation"): [issue.message for issue in issues],
        }
    )


def expected_label(issue: Issue) -> str:
    """How a finding relates to the expected changes file, for the table."""
    if issue.expected_reference is not None:
        return t("ui.expected.matches", reference=issue.expected_reference)
    if issue.rule == "expected_change_missing":
        return t("ui.expected.not_applied")
    if issue.expected_mismatch is not None:
        return t("ui.expected.differs", expected=issue.expected_mismatch)
    return ""


def render_detail_panel(issue: Issue | None, rules: Rules, history: ReviewHistory | None) -> None:
    st.subheader(t("ui.detail.title"))
    if issue is None:
        st.caption(t("ui.detail.hint"))
        return

    explanation = explain_issue(issue, rules)
    with st.container(border=True):
        st.markdown(
            t(
                "ui.detail.header",
                record=issue.record_label,
                category=issue.category.label,
                severity=severity_label(issue.severity),
                review=t("ui.yes") if issue.requires_review else t("ui.no"),
            )
        )
        left, right = st.columns(2)
        with left:
            st.markdown(t("ui.detail.what"))
            st.write(explanation.what_changed)
            st.markdown(t("ui.detail.why"))
            st.write(explanation.why_flagged)
            st.markdown(t("ui.detail.rule"))
            st.code(explanation.rule_triggered, language=None)
        with right:
            st.markdown(t("ui.detail.actions"))
            for action in explanation.suggested_actions:
                st.markdown(f"- {action}")
            st.caption(t("ui.detail.disclaimer"))

        snapshot = record_snapshot(issue, rules)
        if snapshot is not None:
            with st.expander(t("ui.detail.snapshot")):
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

    field_col, previous_col, current_col, changed_col = (
        t("ui.column.field"), t("ui.column.previous"), t("ui.column.current"), t("ui.column.changed"),
    )
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
                field_col: column,
                previous_col: format_for_display(prev_value),
                current_col: format_for_display(curr_value),
                changed_col: t("ui.detail.not_compared") if unavailable else ("" if same else t("ui.detail.changed_yes")),
            }
        )
    if issue.employee_id:
        for dataset in (previous, current):
            candidates = dataset.frame[dataset.frame[KEY_FIELD] == issue.employee_id]
            if len(candidates) > 1:
                # No single candidate is authoritative; expose each for human inspection.
                return pd.DataFrame([
                    {t("ui.column.cycle"): t(f"dataset.{source.name}"), t("ui.column.source_row"): record[SOURCE_ROW],
                     **{field: format_for_display(display_value(field, record.get(field), rules.masked_fields))
                        for field in EXPECTED_COLUMNS}}
                    for source in (previous, current)
                    for record in source.frame[source.frame[KEY_FIELD] == issue.employee_id].to_dict("records")
                ])
    return pd.DataFrame(rows)


def history_display_path(history: ReviewHistory) -> str:
    try:
        return history.path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(history.path)


def render_review_decision(issue: Issue, history: ReviewHistory | None) -> None:
    """Let the operator record what they decided; the engine never does this itself."""
    st.markdown(t("ui.decision.title"))
    if history is None:
        st.caption(t("ui.decision.disabled"))
        return

    if issue.review_status is not ReviewStatus.OPEN:
        st.caption(
            t(
                "ui.decision.current",
                status=issue.review_status.label,
                who=t("ui.decision.by", reviewer=issue.reviewed_by) if issue.reviewed_by else "",
                when=format_timestamp(issue.reviewed_at),
                note=t("ui.decision.note_suffix", note=issue.review_note) if issue.review_note else "",
            )
        )

    key = fingerprint(issue)[:12]  # widgets reset when a different finding is selected
    status_col, note_col, reviewer_col = st.columns([2, 4, 2])
    status = status_col.selectbox(
        t("ui.decision.status"),
        options=list(ReviewStatus),
        index=list(ReviewStatus).index(issue.review_status),
        format_func=lambda s: s.label,
        key=f"status_{key}",
    )
    note = note_col.text_input(t("ui.decision.note"), value=issue.review_note or "", key=f"note_{key}")
    reviewer = reviewer_col.text_input(t("ui.decision.reviewer"), key="reviewer")
    if st.button(t("ui.decision.save"), key=f"save_{key}"):
        save_decision(issue, history, status, note, reviewer)
        st.rerun()
    st.caption(t("ui.decision.help"))


def save_decision(
    issue: Issue, history: ReviewHistory, status: ReviewStatus, note: str, reviewer: str
) -> None:
    """Persist one decision and refresh the result so the table and summary reflect it."""
    history.record(issue, status, note=note, reviewer=reviewer)
    result: ReconciliationResult | None = st.session_state.get("result")
    if result is not None:
        st.session_state["result"] = apply_history(result, history)


def render_ai_explanation(issue: Issue, rules: Rules, explanation: Explanation) -> None:
    st.markdown(t("ui.ai.title"))
    if not llm_available():
        st.caption(t("ui.ai.not_configured"))
        return

    cache: dict[str, str] = st.session_state.setdefault("ai_explanations", {})
    cache_key = issue.model_dump_json()
    if st.button(t("ui.ai.button"), key="ai_button"):
        with st.spinner(t("ui.ai.spinner")):
            cache[cache_key] = explain_with_llm(issue, rules, explanation)
    if cache_key in cache:
        st.write(cache[cache_key])
        st.caption(t("ui.ai.disclaimer"))


def render_exports(result: ReconciliationResult) -> None:
    st.subheader(t("ui.export.title"))
    left, right, _ = st.columns([1, 1, 3])
    left.download_button(
        t("ui.export.full"),
        data=full_report_csv(result),
        file_name="reconciliation_report.csv",
        mime="text/csv",
        width="stretch",
    )
    right.download_button(
        t("ui.export.queue"),
        data=review_queue_csv(result),
        file_name="review_required.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(t("ui.export.caption", total=len(result.issues), queue=len(result.review_queue)))


if __name__ == "__main__":  # Streamlit runs the script as __main__
    main()
