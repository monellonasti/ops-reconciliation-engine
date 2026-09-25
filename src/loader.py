"""Read a CSV export into a clean, string-typed DataFrame with operator-friendly errors.

The loader deals only with the *shape* of the file: encoding, delimiter,
header, column names and row structure. Interpreting the values (numbers,
dates, required fields) is the job of :mod:`src.validators`.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Literal

import pandas as pd

from src.config import Rules
from src.models import EXPECTED_COLUMNS, KEY_FIELD, SOURCE_ROW, Category, Issue

logger = logging.getLogger(__name__)

_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
_DELIMITERS = (",", ";", "\t", "|")


class DatasetLoadError(Exception):
    """A problem with the file itself. The message is written for the operator."""


@dataclass
class LoadedDataset:
    name: Literal["previous", "current"]
    frame: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.frame)


def load_dataset(
    source: bytes | str | Path | IO[bytes] | Any,
    *,
    name: Literal["previous", "current"],
    rules: Rules,
) -> LoadedDataset:
    """Parse ``source`` (bytes, path or file-like) into a :class:`LoadedDataset`.

    Raises :class:`DatasetLoadError` for problems that make the file unusable.
    Row-level problems (wrong number of fields) become issues and the row is skipped.
    """
    raw = _read_bytes(source)
    if not raw.strip():
        raise DatasetLoadError("The file is empty.")

    text, encoding = _decode(raw)
    notes: list[str] = []
    if encoding != "utf-8-sig":
        notes.append(f"File was not UTF-8; decoded as {encoding}.")

    delimiter = _detect_delimiter(text)
    header, rows, issues = _parse_rows(text, delimiter, name, rules)

    frame = pd.DataFrame([cells for _, cells in rows], columns=header, dtype=object)
    frame = frame.map(_clean_cell)
    frame[SOURCE_ROW] = [line_number for line_number, _ in rows]

    frame, column_notes = _align_columns(frame, rules)
    notes.extend(column_notes)

    logger.info("Loaded %s dataset: %d rows, %d skipped", name, len(frame), len(issues))
    return LoadedDataset(name=name, frame=frame, issues=issues, notes=notes)


# --- reading ---------------------------------------------------------------


def _read_bytes(source: Any) -> bytes:
    if isinstance(source, bytes):
        return source
    if hasattr(source, "getvalue"):  # Streamlit UploadedFile, BytesIO
        return source.getvalue()
    if hasattr(source, "read"):
        data = source.read()
        return data.encode("utf-8") if isinstance(data, str) else data
    path = Path(source)
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise DatasetLoadError(f"File not found: {path.name}") from exc
    except OSError as exc:
        raise DatasetLoadError(f"Could not read {path.name}: {exc.strerror}") from exc


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DatasetLoadError("The file encoding is not supported. Save it as UTF-8 and retry.")


def _detect_delimiter(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    counts = {delimiter: first_line.count(delimiter) for delimiter in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# --- parsing ---------------------------------------------------------------


def _parse_rows(
    text: str, delimiter: str, name: str, rules: Rules
) -> tuple[list[str], list[tuple[int, list[str]]], list[Issue]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header_cells = next(reader)
    except StopIteration as exc:
        raise DatasetLoadError("The file has no header row.") from exc
    except csv.Error as exc:
        raise DatasetLoadError(f"The file could not be parsed as CSV: {exc}") from exc

    header = [_normalize_column_name(cell) for cell in header_cells]
    _check_header(header)

    rows: list[tuple[int, list[str]]] = []
    issues: list[Issue] = []
    try:
        for cells in reader:
            line_number = reader.line_num
            if not any(cell.strip() for cell in cells):
                continue  # blank line, common at the end of hand-edited exports
            if len(cells) != len(header):
                issues.append(_malformed_row_issue(line_number, len(cells), len(header), name, rules))
                continue
            rows.append((line_number, cells))
    except csv.Error as exc:
        raise DatasetLoadError(
            f"The file could not be parsed as CSV near line {reader.line_num}: {exc}"
        ) from exc

    if not rows:
        raise DatasetLoadError("The file has a header but no data rows.")
    return header, rows, issues


def _normalize_column_name(cell: str) -> str:
    return cell.strip().strip('"').strip().lower().replace(" ", "_")


def _check_header(header: list[str]) -> None:
    if not any(header):
        raise DatasetLoadError("The file has no header row.")
    blanks = [index + 1 for index, name in enumerate(header) if not name]
    if blanks:
        raise DatasetLoadError(f"Header has unnamed column(s) at position {blanks}.")
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in header:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise DatasetLoadError(f"Duplicate column name(s): {', '.join(duplicates)}.")


def _clean_cell(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _malformed_row_issue(line: int, found: int, expected: int, name: str, rules: Rules) -> Issue:
    severity = rules.invalid_values.severity
    return Issue(
        employee_id=None,
        row_number=line,
        dataset=name,  # type: ignore[arg-type]
        category=Category.INVALID_VALUE,
        field=None,
        rule="malformed_row",
        severity=severity,
        requires_review=rules.requires_review(severity),
        message=f"Row {line} has {found} fields, expected {expected}; the row was skipped.",
    )


# --- columns ---------------------------------------------------------------


def _align_columns(frame: pd.DataFrame, rules: Rules) -> tuple[pd.DataFrame, list[str]]:
    """Fail on missing required columns, tolerate missing optional ones, keep extras."""
    required = [KEY_FIELD] + [f for f in rules.required_fields if f != KEY_FIELD]
    missing_required = [column for column in required if column not in frame.columns]
    if missing_required:
        raise DatasetLoadError(
            f"Missing required column(s): {', '.join(missing_required)}. "
            f"Found: {', '.join(c for c in frame.columns if c != SOURCE_ROW)}."
        )

    notes: list[str] = []
    missing_optional = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing_optional:
        for column in missing_optional:
            frame[column] = None
        notes.append(
            "Optional column(s) not present, related checks skipped: "
            + ", ".join(missing_optional)
        )

    extra = [c for c in frame.columns if c not in EXPECTED_COLUMNS and c != SOURCE_ROW]
    if extra:
        notes.append("Column(s) not used by any rule: " + ", ".join(extra))

    return frame, notes
