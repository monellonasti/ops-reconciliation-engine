"""Read a CSV or Excel export into a clean DataFrame with operator-friendly errors.

The loader deals only with the *shape* of the file: encoding, delimiter,
header, column names and row structure. Interpreting the values (numbers,
dates, required fields) is the job of :mod:`src.validators`.

:func:`read_table` is the generic part (any CSV or ``.xlsx`` with a header);
:func:`load_dataset` adds the employee schema on top of it.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import IO, Any, Literal

import pandas as pd

from src.config import Rules
from src.i18n import t
from src.models import EXPECTED_COLUMNS, KEY_FIELD, SOURCE_ROW, Category, Issue
from src.utils import redact_iban_text

logger = logging.getLogger(__name__)

_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
_DELIMITERS = (",", ";", "\t", "|")
_XLSX_MAGIC = b"PK\x03\x04"  # .xlsx files are zip archives

Source = bytes | str | Path | IO[bytes] | Any
Cell = str | float | int | datetime | date | None


class DatasetLoadError(Exception):
    """A problem with the file itself. The message is written for the operator."""

    def __init__(self, message: str):
        super().__init__(redact_iban_text(message))


@dataclass
class ParsedTable:
    """A file reduced to a header and clean rows (None for blank cells).

    CSV cells are text. Excel cells keep their type: numbers stay numbers and
    dates stay dates, so the validators do not have to guess a text convention.
    """

    header: list[str]
    rows: list[tuple[int, list[Cell]]]
    skipped: list[tuple[int, int]] = field(default_factory=list)  # (line, fields found)
    notes: list[str] = field(default_factory=list)

    def records(self) -> list[dict[str, Any]]:
        return [
            {**dict(zip(self.header, cells, strict=True)), SOURCE_ROW: line}
            for line, cells in self.rows
        ]


@dataclass
class LoadedDataset:
    name: Literal["previous", "current"]
    frame: pd.DataFrame
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    missing_columns: set[str] = field(default_factory=set)

    @property
    def record_count(self) -> int:
        return len(self.frame)


def read_table(source: Source) -> ParsedTable:
    """Parse any CSV or ``.xlsx`` file with a header row.

    CSV rows with the wrong number of fields are skipped and listed in
    ``skipped``; file-level problems raise :class:`DatasetLoadError`.
    """
    raw = _read_bytes(source)
    if not raw.strip():
        raise DatasetLoadError(t("loader.empty"))
    if raw[:4] == _XLSX_MAGIC:
        header, rows, notes = _read_excel(raw)
        return ParsedTable(header=header, rows=rows, notes=notes)

    text, encoding = _decode(raw)
    if "\x00" in text:
        raise DatasetLoadError(t("loader.nul"))
    notes: list[str] = []
    if encoding != "utf-8-sig":
        notes.append(t("loader.not_utf8", encoding=encoding))

    header, rows, skipped = _parse_csv(text, _detect_delimiter(text))
    cleaned = [(line, [_clean_cell(cell) for cell in cells]) for line, cells in rows]
    return ParsedTable(header=header, rows=cleaned, skipped=skipped, notes=notes)


def load_dataset(source: Source, *, name: Literal["previous", "current"], rules: Rules) -> LoadedDataset:
    """Parse ``source`` (bytes, path or file-like) into a :class:`LoadedDataset`.

    Raises :class:`DatasetLoadError` for problems that make the file unusable.
    Row-level problems (wrong number of fields) become issues and the row is skipped.
    """
    table = read_table(source)
    issues = [
        _malformed_row_issue(line, found, len(table.header), name, rules)
        for line, found in table.skipped
    ]

    # Plain Python objects (None for blanks) on purpose: the rule functions iterate
    # row by row, and object columns are much cheaper to iterate than Arrow strings.
    frame = pd.DataFrame([cells for _, cells in table.rows], columns=table.header, dtype=object)
    frame[SOURCE_ROW] = [line for line, _ in table.rows]

    frame, column_notes = _align_columns(frame, rules)
    frame[KEY_FIELD] = frame[KEY_FIELD].map(_key_text)
    notes = table.notes + column_notes

    logger.info("Loaded %s dataset: %d rows, %d skipped", name, len(frame), len(issues))
    return LoadedDataset(
        name=name,
        frame=frame,
        issues=issues,
        notes=[redact_iban_text(note) for note in notes],
        missing_columns=set(EXPECTED_COLUMNS) - set(table.header),
    )


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
        raise DatasetLoadError(t("loader.not_found", name=path.name)) from exc
    except OSError as exc:
        raise DatasetLoadError(t("loader.unreadable", name=path.name, error=exc.strerror)) from exc


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DatasetLoadError(t("loader.encoding"))


def _detect_delimiter(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    counts = {delimiter: first_line.count(delimiter) for delimiter in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


# --- CSV parsing -------------------------------------------------------------


def _parse_csv(
    text: str, delimiter: str
) -> tuple[list[str], list[tuple[int, list[str]]], list[tuple[int, int]]]:
    # newline="" hands line endings to the csv module untouched, so CR-only files
    # (older Mac exports) are split into rows like CRLF and LF files.
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        header_cells = next(reader)
    except StopIteration as exc:
        raise DatasetLoadError(t("loader.no_header")) from exc
    except csv.Error as exc:
        raise DatasetLoadError(t("loader.parse_error", error=exc)) from exc

    header = [_normalize_column_name(cell) for cell in header_cells]
    _check_header(header)

    rows: list[tuple[int, list[str]]] = []
    skipped: list[tuple[int, int]] = []
    try:
        for cells in reader:
            line_number = reader.line_num
            if not any(cell.strip() for cell in cells):
                continue  # blank line, common at the end of hand-edited exports
            if len(cells) != len(header):
                skipped.append((line_number, len(cells)))
                continue
            rows.append((line_number, cells))
    except csv.Error as exc:
        raise DatasetLoadError(t("loader.parse_error_near", line=reader.line_num, error=exc)) from exc

    if not rows:
        raise DatasetLoadError(t("loader.no_rows"))
    return header, rows, skipped


# --- Excel parsing -----------------------------------------------------------


def _read_excel(raw: bytes) -> tuple[list[str], list[tuple[int, list[Cell]]], list[str]]:
    """First sheet of an .xlsx workbook: row 1 is the header, values keep their types."""
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # broken zip, wrong format, missing dependency: all the same to the operator
        raise DatasetLoadError(t("loader.excel_error")) from exc

    try:
        sheet = workbook.worksheets[0]
        notes = []
        if len(workbook.worksheets) > 1:
            notes.append(t("loader.excel_sheet", sheet=sheet.title, count=len(workbook.worksheets)))
        lines = sheet.iter_rows(values_only=True)
        header_cells = list(next(lines, ()))
        while header_cells and _clean_excel_cell(header_cells[-1]) is None:
            header_cells.pop()  # Excel pads the used range with empty trailing columns
        if not header_cells:
            raise DatasetLoadError(t("loader.no_header"))
        header = [_normalize_column_name(str(_clean_excel_cell(cell) or "")) for cell in header_cells]
        _check_header(header)

        rows: list[tuple[int, list[Cell]]] = []
        for index, cells in enumerate(lines, start=2):
            values = [_clean_excel_cell(cell) for cell in cells[: len(header)]]
            values += [None] * (len(header) - len(values))
            if all(value is None for value in values):
                continue
            rows.append((index, values))
    except DatasetLoadError:
        raise
    except Exception as exc:
        # A damaged sheet fails while rows are read, and the library's message can
        # quote the offending cell (an IBAN, a salary): never pass it on.
        raise DatasetLoadError(t("loader.excel_error")) from exc
    finally:
        workbook.close()

    if not rows:
        raise DatasetLoadError(t("loader.no_rows"))
    return header, rows, notes


def _clean_excel_cell(value: Any) -> Cell:
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    if isinstance(value, (int, float, datetime, date)):
        return value
    text = str(value).strip()
    return text or None


# --- shared -----------------------------------------------------------------


def _normalize_column_name(cell: str) -> str:
    return cell.strip().strip('"').strip().lower().replace(" ", "_")


def _check_header(header: list[str]) -> None:
    if SOURCE_ROW in header:
        raise DatasetLoadError(t("loader.reserved_header"))
    if not any(header):
        raise DatasetLoadError(t("loader.no_header"))
    blanks = [index + 1 for index, name in enumerate(header) if not name]
    if blanks:
        raise DatasetLoadError(t("loader.unnamed_columns", positions=blanks))
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in header:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise DatasetLoadError(t("loader.duplicate_columns", names=", ".join(duplicates)))


def _key_text(value: Cell) -> str | None:
    """Record keys are identifiers: an Excel number 125 is the ID "125", not 125 or 125.0."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


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
        message=t("loader.malformed_row", line=line, found=found, expected=expected),
    )


# --- columns ---------------------------------------------------------------


def _align_columns(frame: pd.DataFrame, rules: Rules) -> tuple[pd.DataFrame, list[str]]:
    """Fail on missing required columns, tolerate missing optional ones, keep extras."""
    required = [KEY_FIELD] + [f for f in rules.required_fields if f != KEY_FIELD]
    missing_required = [column for column in required if column not in frame.columns]
    if missing_required:
        raise DatasetLoadError(
            t(
                "loader.missing_required_columns",
                missing=", ".join(missing_required),
                found=", ".join(c for c in frame.columns if c != SOURCE_ROW),
            )
        )

    notes: list[str] = []
    missing_optional = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing_optional:
        for column in missing_optional:
            frame[column] = None
        notes.append(t("loader.optional_missing", columns=", ".join(missing_optional)))

    extra = [c for c in frame.columns if c not in EXPECTED_COLUMNS and c != SOURCE_ROW]
    if extra:
        notes.append(t("loader.extra_columns", columns=", ".join(extra)))

    return frame, notes
