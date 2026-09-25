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
from src.loader import DatasetLoadError, LoadedDataset, load_dataset
from src.models import ReconciliationResult
from src.reconciliation import reconcile
from src.reporting import build_summary, full_report_csv, review_queue_csv, sort_issues
from src.validators import validate_dataset

logger = logging.getLogger(__name__)


def run_reconciliation(
    previous: LoadedDataset, current: LoadedDataset, rules: Rules
) -> ReconciliationResult:
    """Full pipeline on two already-loaded datasets."""
    previous_validated = validate_dataset(previous, rules)
    current_validated = validate_dataset(current, rules)

    issues = [
        *previous.issues,
        *current.issues,
        *previous_validated.issues,
        *current_validated.issues,
        *reconcile(previous_validated, current_validated, rules),
        *detect_anomalies(current_validated, rules),
    ]
    issues = sort_issues(issues)
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
    return ReconciliationResult(issues=issues, summary=summary, notes=previous.notes + current.notes)


def reconcile_sources(
    previous_source: bytes | str | Path | IO[bytes] | Any,
    current_source: bytes | str | Path | IO[bytes] | Any,
    rules: Rules | None = None,
) -> ReconciliationResult:
    """Convenience wrapper: load both sources and run the pipeline."""
    rules = rules or load_rules()
    previous = load_dataset(previous_source, name="previous", rules=rules)
    current = load_dataset(current_source, name="current", rules=rules)
    return run_reconciliation(previous, current, rules)


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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        rules = load_rules(args.rules)
        result = reconcile_sources(args.previous, args.current, rules)
    except (DatasetLoadError, RulesConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "reconciliation_report.csv").write_bytes(full_report_csv(result))
    (args.output_dir / "review_required.csv").write_bytes(review_queue_csv(result))

    summary = result.summary
    print(f"Records processed: {summary.current_records} (previous cycle: {summary.previous_records})")
    print(f"New: {summary.new_records}  Removed: {summary.removed_records}  Changes: {summary.changes_detected}")
    print(f"Critical: {summary.critical_issues}  Warnings: {summary.warnings}  Info: {summary.info}")
    print(f"Records requiring review: {summary.records_requiring_review}")
    print(f"Reports written to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
