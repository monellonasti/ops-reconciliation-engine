"""Excel (.xlsx) input: typed cells, blank rows, several sheets, broken files."""

from __future__ import annotations

import io
from datetime import date, datetime

import openpyxl
import pytest

from src.config import Rules
from src.engine import reconcile_sources
from src.expectations import load_expected_changes
from src.loader import DatasetLoadError, load_dataset, read_table
from src.models import EXPECTED_COLUMNS, SOURCE_ROW
from tests.conftest import BASE_RECORD, csv_bytes, employee


def workbook_bytes(rows: list[list[object]], header: list[str] | None = None, sheets: int = 1) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Export"
    sheet.append(header or list(EXPECTED_COLUMNS))
    for row in rows:
        sheet.append(row)
    for extra in range(1, sheets):
        book.create_sheet(f"Sheet{extra}").append(["ignored"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def typed_row(**overrides: object) -> list[object]:
    """The base record as Excel would store it: numbers as numbers, dates as datetimes."""
    record: dict[str, object] = dict(BASE_RECORD)
    record.update(
        working_hours=40,
        monthly_salary=2100,
        bonus=0,
        overtime_hours=4,
        start_date=datetime(2020, 1, 15),
        end_date=None,
    )
    record.update(overrides)
    return [record[column] for column in EXPECTED_COLUMNS]


def test_xlsx_is_detected_and_cells_keep_their_types(rules):
    loaded = load_dataset(workbook_bytes([typed_row(), typed_row(employee_id="EMP-00002", monthly_salary=2500.5)]), name="current", rules=rules)

    assert loaded.record_count == 2
    assert list(loaded.frame[SOURCE_ROW]) == [2, 3]
    assert loaded.frame.loc[0, "monthly_salary"] == 2100
    assert loaded.frame.loc[1, "monthly_salary"] == 2500.5
    assert isinstance(loaded.frame.loc[0, "start_date"], datetime)
    assert loaded.frame.loc[0, "end_date"] is None
    assert loaded.issues == [] and loaded.notes == []


def test_xlsx_and_csv_give_the_same_findings(rules):
    previous_csv = csv_bytes([employee(monthly_salary="2100")])
    current_csv = csv_bytes([employee(monthly_salary="3000", end_date="2024-09-30", overtime_hours="72")])
    current_xlsx = workbook_bytes([typed_row(monthly_salary=3000, end_date=datetime(2024, 9, 30), overtime_hours=72)])

    from_csv = reconcile_sources(previous_csv, current_csv, rules)
    from_xlsx = reconcile_sources(previous_csv, current_xlsx, rules)

    strip = lambda result: [issue.model_dump(exclude={"row_number"}) for issue in result.issues]  # noqa: E731
    assert strip(from_xlsx) == strip(from_csv)
    assert from_xlsx.summary == from_csv.summary


def test_excel_numbers_are_not_affected_by_the_text_number_convention():
    from src.config import REPO_ROOT, load_rules

    italian = load_rules(REPO_ROOT / "rules" / "validation_rules.it.yaml")
    current = workbook_bytes([typed_row(monthly_salary=2100.5)])

    result = reconcile_sources(current, current, italian)

    assert [issue.rule for issue in result.issues] == []


def test_blank_rows_and_trailing_empty_columns_are_ignored(rules):
    header = list(EXPECTED_COLUMNS) + [None, None]
    rows = [typed_row() + [None, None], [None] * (len(EXPECTED_COLUMNS) + 2), typed_row(employee_id="EMP-00002") + [None, None]]

    loaded = load_dataset(workbook_bytes(rows, header=header), name="current", rules=rules)

    assert list(loaded.frame["employee_id"]) == ["EMP-00001", "EMP-00002"]
    assert list(loaded.frame[SOURCE_ROW]) == [2, 4]
    assert "extra" not in loaded.notes


def test_only_the_first_sheet_is_read_with_a_note(rules):
    loaded = load_dataset(workbook_bytes([typed_row()], sheets=3), name="current", rules=rules)

    assert loaded.record_count == 1
    assert any("first sheet 'Export'" in note and "3 sheets" in note for note in loaded.notes)


def test_broken_xlsx_gives_a_clean_error(rules):
    with pytest.raises(DatasetLoadError, match="Excel file could not be read"):
        load_dataset(b"PK\x03\x04not really a workbook", name="current", rules=rules)


def test_header_only_workbook_is_rejected(rules):
    with pytest.raises(DatasetLoadError, match="no data rows"):
        load_dataset(workbook_bytes([]), name="current", rules=rules)


def test_missing_required_column_in_xlsx_is_reported(rules):
    header = [column for column in EXPECTED_COLUMNS if column != "monthly_salary"]
    rows = [[value for column, value in zip(EXPECTED_COLUMNS, typed_row(), strict=True) if column != "monthly_salary"]]

    with pytest.raises(DatasetLoadError, match="Missing required column.*monthly_salary"):
        load_dataset(workbook_bytes(rows, header=header), name="current", rules=rules)


def test_expected_changes_can_be_an_xlsx_with_typed_values():
    book = workbook_bytes(
        [["EMP-00001", "monthly_salary", 3000, "HR-1"], ["EMP-00001", "end_date", date(2024, 9, 30), "leaver"]],
        header=["employee_id", "field", "expected_value", "reference"],
    )

    changes = load_expected_changes(book)

    assert changes.lookup("EMP-00001", "monthly_salary").expected_value == "3000"
    assert changes.lookup("EMP-00001", "end_date").expected_value == "2024-09-30"
    result = reconcile_sources(
        csv_bytes([employee(monthly_salary="2100")]),
        csv_bytes([employee(monthly_salary="3000", end_date="2024-09-30")]),
        Rules(),
        expected_source=book,
    )
    assert result.summary.expected_matched == 2


def test_read_table_reports_the_sheet_shape():
    table = read_table(workbook_bytes([typed_row()]))

    assert table.header == list(EXPECTED_COLUMNS)
    assert table.skipped == []
    assert table.records()[0]["monthly_salary"] == 2100
