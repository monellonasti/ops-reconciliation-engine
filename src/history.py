"""Review history: remember the decision an operator took on a finding.

Findings are identified by a fingerprint of what the operator saw (record,
rule, field, previous and current value as displayed). When the same finding
comes back in a later cycle, the stored decision is attached to it, so an
accepted exception does not return to the queue and a known problem is
shown as such.

Storage is a single SQLite file. Nothing is written until an operator records
a decision; reading from a file that does not exist yields no decisions and
does not create it. The engine never changes a decision on its own.

A file that cannot be used (damaged, locked, not writable) raises
:class:`HistoryError` with a message for the operator; callers show it and
carry on without decisions instead of failing the whole run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from src.config import REPO_ROOT, Rules
from src.i18n import en, t
from src.models import Issue, ReviewStatus
from src.utils import normalize_text, redact_iban_text

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    fingerprint    TEXT PRIMARY KEY,
    record         TEXT NOT NULL,
    rule           TEXT NOT NULL,
    field          TEXT,
    previous_value TEXT,
    current_value  TEXT,
    status         TEXT NOT NULL,
    note           TEXT,
    reviewer       TEXT,
    decided_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint    TEXT NOT NULL,
    record         TEXT NOT NULL,
    rule           TEXT NOT NULL,
    field          TEXT,
    action         TEXT NOT NULL,
    status         TEXT,
    note           TEXT,
    reviewer       TEXT,
    decided_at     TEXT NOT NULL
);
"""
_LOOKUP_CHUNK = 500


class HistoryError(Exception):
    """The history file cannot be read or written. The message is written for the operator."""


class Decision(BaseModel):
    status: ReviewStatus
    note: str | None = None
    reviewer: str | None = None
    decided_at: str


def fingerprint(issue: Issue) -> str:
    """Stable identity of a finding across runs: what was flagged and the values shown.

    The record part does not depend on the interface language, so a decision
    saved in one language still applies after switching to another.
    """
    parts = [_record_identity(issue), issue.rule, issue.field, issue.previous_value, issue.current_value]
    return hashlib.sha256(json.dumps(parts, default=str).encode("utf-8")).hexdigest()


def _record_identity(issue: Issue) -> str:
    # Rows without an ID use the English label, which is what fingerprints were built
    # from before other languages existed: decisions saved back then stay attached.
    if issue.employee_id:
        return issue.employee_id
    if issue.row_number is not None:
        return str(en.MESSAGES["record.row"]).format(line=issue.row_number)
    return str(en.MESSAGES["record.unknown"])


class ReviewHistory:
    def __init__(self, path: Path):
        self.path = Path(path)

    # --- reading --------------------------------------------------------------

    def lookup(self, issues: list[Issue]) -> dict[str, Decision]:
        """Decisions for the given findings, keyed by fingerprint."""
        if not issues or not self.path.exists():
            return {}
        prints = sorted({fingerprint(issue) for issue in issues})
        found: dict[str, Decision] = {}
        with self._usable(), closing(self._connect()) as connection:
            for start in range(0, len(prints), _LOOKUP_CHUNK):
                chunk = prints[start : start + _LOOKUP_CHUNK]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT fingerprint, status, note, reviewer, decided_at FROM decisions "
                    f"WHERE fingerprint IN ({placeholders})",
                    chunk,
                )
                for row in rows:
                    found[row[0]] = Decision(
                        status=ReviewStatus(row[1]), note=row[2], reviewer=row[3], decided_at=row[4]
                    )
        return found

    def apply(self, issues: list[Issue]) -> list[Issue]:
        """Copies of ``issues`` carrying the stored decision, if any."""
        decisions = self.lookup(issues)
        annotated = []
        for issue in issues:
            decision = decisions.get(fingerprint(issue))
            if decision is None:
                annotated.append(issue if issue.review_status is ReviewStatus.OPEN else _reset(issue))
            else:
                annotated.append(
                    issue.model_copy(
                        update={
                            "review_status": decision.status,
                            "review_note": decision.note,
                            "reviewed_by": decision.reviewer,
                            "reviewed_at": decision.decided_at,
                        }
                    )
                )
        return annotated

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._usable(), closing(self._connect()) as connection:
            return connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    def version(self) -> tuple[int, int] | None:
        """Changes whenever a decision is saved, from this session or any other."""
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    # --- writing --------------------------------------------------------------

    def record(
        self, issue: Issue, status: ReviewStatus, note: str | None = None, reviewer: str | None = None
    ) -> Decision:
        """Store (or replace) the decision for one finding. OPEN clears it."""
        if status is ReviewStatus.OPEN:
            self.clear(issue, reviewer=reviewer)
            return Decision(status=ReviewStatus.OPEN, decided_at=_now())

        decision = Decision(
            status=status,
            note=_clean(note),
            reviewer=_clean(reviewer),
            decided_at=_now(),
        )
        key = fingerprint(issue)
        with self._usable(), closing(self._connect(create=True)) as connection, connection:
            connection.execute(
                "INSERT INTO decisions (fingerprint, record, rule, field, previous_value, current_value,"
                " status, note, reviewer, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(fingerprint) DO UPDATE SET status=excluded.status, note=excluded.note,"
                " reviewer=excluded.reviewer, decided_at=excluded.decided_at",
                (
                    key,
                    issue.record_label,
                    issue.rule,
                    issue.field,
                    _text(issue.previous_value),
                    _text(issue.current_value),
                    decision.status.value,
                    decision.note,
                    decision.reviewer,
                    decision.decided_at,
                ),
            )
            self._log(connection, key, issue, "set", decision)
        return decision

    def clear(self, issue: Issue, reviewer: str | None = None) -> None:
        """Forget the decision for one finding; it goes back to the open queue."""
        if not self.path.exists():
            return
        key = fingerprint(issue)
        with self._usable(), closing(self._connect()) as connection, connection:
            deleted = connection.execute("DELETE FROM decisions WHERE fingerprint = ?", (key,)).rowcount
            if deleted:
                cleared = Decision(status=ReviewStatus.OPEN, reviewer=_clean(reviewer), decided_at=_now())
                self._log(connection, key, issue, "clear", cleared)

    # --- internals ------------------------------------------------------------

    @contextmanager
    def _usable(self) -> Iterator[None]:
        """Turn storage failures into one operator message. Only the error type is logged."""
        try:
            yield
        except sqlite3.OperationalError as exc:
            logger.warning("Review history unusable: %s", type(exc).__name__)
            key = "history.busy" if "locked" in str(exc).lower() else "history.unavailable"
            raise HistoryError(t(key, path=self.path.name)) from exc
        except (sqlite3.Error, OSError, ValueError) as exc:
            logger.warning("Review history unusable: %s", type(exc).__name__)
            raise HistoryError(t("history.unavailable", path=self.path.name)) from exc

    def _connect(self, create: bool = False) -> sqlite3.Connection:
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            connection.executescript(_SCHEMA)
        except BaseException:
            connection.close()  # an open handle would keep the file locked on Windows
            raise
        return connection

    @staticmethod
    def _log(connection: sqlite3.Connection, key: str, issue: Issue, action: str, decision: Decision) -> None:
        connection.execute(
            "INSERT INTO decision_log (fingerprint, record, rule, field, action, status, note, reviewer,"
            " decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                issue.record_label,
                issue.rule,
                issue.field,
                action,
                decision.status.value,
                decision.note,
                decision.reviewer,
                decision.decided_at,
            ),
        )


def open_history(rules: Rules) -> ReviewHistory | None:
    """The configured history, or None when disabled in the rules file."""
    if not rules.history.enabled:
        return None
    path = Path(rules.history.path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return ReviewHistory(path)


def _reset(issue: Issue) -> Issue:
    return issue.model_copy(
        update={"review_status": ReviewStatus.OPEN, "review_note": None, "reviewed_by": None, "reviewed_at": None}
    )


def _clean(text: str | None) -> str | None:
    cleaned = normalize_text(text)
    return redact_iban_text(cleaned) if cleaned else None


def _text(value: str | float | None) -> str | None:
    return None if value is None else str(value)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
