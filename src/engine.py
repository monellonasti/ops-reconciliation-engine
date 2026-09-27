"""Orchestrates one reconciliation run: validate both cycles, compare, detect anomalies.

Also usable from the command line for scheduled or scripted runs::

    python -m src.engine data/demo_previous.csv data/demo_current.csv --output-dir reports
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import IO, Any

from src.anomaly_detection import detect_anomalies
from src.config import Rules, RulesConfigError, load_rules
from src.expectations import ExpectedChanges, load_expected_changes
from src.history import ReviewHistory, open_history
from src.i18n import set_language, t
from src.loader import DatasetLoadError, LoadedDataset, load_dataset
from src.models import ReconciliationResult, ReviewStatus
from src.reconciliation import reconcile
from src.reporting import build_summary, full_report_csv, review_queue_csv, sort_issues
from src.utils import configure_formats
from src.validators import validate_dataset

logger = logging.getLogger(__name__)


def apply_presentation(rules: Rules) -> None:
    """Select the language and the number/date formats of the rules for everything that follows."""
    set_language(rules.language)
    configure_formats(**rules.formats.model_dump())


def run_reconciliation(
    previous: LoadedDataset,
    current: LoadedDataset,
    rules: Rules,
    history: ReviewHistory | None = None,
    expected: ExpectedChanges | None = None,
) -> ReconciliationResult:
    """Full pipeline on two already-loaded datasets.

    With a ``history``, findings an operator already decided on carry that decision.
    With ``expected`` changes, approved changes are downgraded and missing ones reported.
    """
    apply_presentation(rules)
    previous_validated = validate_dataset(previous, rules)
    current_validated = validate_dataset(current, rules)

    issues = [
        *previous.issues,
        *current.issues,
        *previous_validated.issues,
        *current_validated.issues,
        *reconcile(previous_validated, current_validated, rules, expected),
        *detect_anomalies(current_validated, rules),
    ]
    issues = sort_issues(issues)
    if history is not None:
        issues = history.apply(issues)
    summary = build_summary(
        issues,
        previous_records=previous.record_count,
        current_records=current.record_count,
    )
    logger.info(
        "Reconciliation complete: %d issues (%d critical, %d warnings), %d records to review",
        summary.total_issues,
        summary.critical_issues,
        summary.warnings,
        summary.records_requiring_review,
    )
    notes = previous.notes + current.notes
    if previous.issues or current.issues:
        notes.append(t("note.rows_skipped"))
    if any(issue.rule == "duplicate_employee_id" for issue in issues):
        notes.append(t("note.duplicates_excluded"))
    if expected is not None:
        notes.append(
            t(
                "note.expected",
                listed=len(expected),
                matched=summary.expected_matched,
                mismatched=summary.expected_mismatched,
                missing=summary.expected_missing,
            )
        )
    return ReconciliationResult(issues=issues, summary=summary, notes=notes)


def reconcile_sources(
    previous_source: bytes | str | Path | IO[bytes] | Any,
    current_source: bytes | str | Path | IO[bytes] | Any,
    rules: Rules | None = None,
    history: ReviewHistory | None = None,
    expected_source: bytes | str | Path | IO[bytes] | Any | None = None,
) -> ReconciliationResult:
    """Convenience wrapper: load the sources and run the pipeline."""
    rules = rules or load_rules()
    previous = load_dataset(previous_source, name="previous", rules=rules)
    current = load_dataset(current_source, name="current", rules=rules)
    expected = load_expected_changes(expected_source) if expected_source is not None else None
    return run_reconciliation(previous, current, rules, history, expected)


def apply_history(result: ReconciliationResult, history: ReviewHistory) -> ReconciliationResult:
    """Re-attach stored decisions to an existing result (after an operator saved one)."""
    issues = history.apply(result.issues)
    summary = build_summary(
        issues,
        previous_records=result.summary.previous_records,
        current_records=result.summary.current_records,
    )
    return ReconciliationResult(issues=issues, summary=summary, notes=result.notes)


# --- command line ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.engine",
        description="Reconcile two CSV cycles and write the report files.",
    )
    parser.add_argument("previous", type=Path, help="CSV export of the previous cycle")
    parser.add_argument("current", type=Path, help="CSV export of the current cycle")
    parser.add_argument("--rules", type=Path, default=None, help="rules YAML (default: rules/validation_rules.yaml)")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="where to write the CSV reports")
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="optional CSV of approved changes (employee_id, field, expected_value, reference)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        rules = load_rules(args.rules)
        result = reconcile_sources(
            args.previous,
            args.current,
            rules,
            history=open_history(rules),
            expected_source=args.expected,
        )
    except (DatasetLoadError, RulesConfigError) as exc:
        print(t("cli.error", error=exc), file=sys.stderr)
        return 1

    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "reconciliation_report.csv").write_bytes(full_report_csv(result))
        (args.output_dir / "review_required.csv").write_bytes(review_queue_csv(result))
    except OSError:
        print(t("cli.write_error"), file=sys.stderr)
        return 1

    summary = result.summary
    print(t("cli.records", current=summary.current_records, previous=summary.previous_records))
    print(t("cli.counts", new=summary.new_records, removed=summary.removed_records, changes=summary.changes_detected))
    print(t("cli.severities", critical=summary.critical_issues, warnings=summary.warnings, info=summary.info))
    print(t("cli.review", count=summary.records_requiring_review))
    for note in result.notes:
        print(t("cli.note", note=note))
    decided = sum(issue.review_status is not ReviewStatus.OPEN for issue in result.issues)
    if decided:
        print(
            t(
                "cli.decided",
                decided=decided,
                accepted=summary.accepted_findings,
                needs_action=summary.needs_action_findings,
            )
        )
    print(t("cli.written", path=args.output_dir.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
