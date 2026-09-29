"""Structural loading: encodings, delimiters, headers, malformed rows."""

from __future__ import annotations

import pytest

from src.loader import DatasetLoadError, load_dataset
from src.models import EXPECTED_COLUMNS, SOURCE_ROW
from tests.conftest import csv_bytes, employee


def test_loads_well_formed_csv(make_loaded):
    loaded = make_loaded([employee(), employee(employee_id="EMP-00002", end_date="")])

    assert loaded.record_count == 2
    assert list(loaded.frame[SOURCE_ROW]) == [2, 3]
    assert loaded.frame.loc[0, "employee_id"] == "EMP-00001"
    assert loaded.frame.loc[0, "end_date"] is None  # blank cells become None
    assert loaded.issues == []


def test_column_names_are_normalized(rules):
    raw = b"Employee ID,First Name,LAST_NAME,contract_type,monthly_salary\nEMP-1,Ada,Rossi,full_time,2000\n"

    loaded = load_dataset(raw, name="current", rules=rules)

    assert {"employee_id", "first_name", "last_name"} <= set(loaded.frame.columns)


def test_cells_are_stripped(rules):
    raw = b"employee_id,first_name,last_name,contract_type,monthly_salary\n  EMP-1 , Ada ,Rossi,full_time, 2000 \n"

    loaded = load_dataset(raw, name="current", rules=rules)

    assert loaded.frame.loc[0, "employee_id"] == "EMP-1"
    assert loaded.frame.loc[0, "monthly_salary"] == "2000"


def test_empty_file_is_rejected(rules):
    with pytest.raises(DatasetLoadError, match="empty"):
        load_dataset(b"", name="current", rules=rules)
    with pytest.raises(DatasetLoadError, match="empty"):
        load_dataset(b"   \n\n", name="current", rules=rules)


def test_header_only_is_rejected(rules):
    with pytest.raises(DatasetLoadError, match="no data rows"):
        load_dataset(csv_bytes([]), name="current", rules=rules)


def test_duplicate_column_names_are_rejected(rules):
    raw = b"employee_id,first_name,first_name,last_name,contract_type,monthly_salary\nEMP-1,Ada,Ada,Rossi,full_time,2000\n"

    with pytest.raises(DatasetLoadError, match="Duplicate column name.*first_name"):
        load_dataset(raw, name="current", rules=rules)


def test_missing_required_column_is_rejected(rules):
    columns = [column for column in EXPECTED_COLUMNS if column != "monthly_salary"]

    with pytest.raises(DatasetLoadError, match="Missing required column.*monthly_salary"):
        load_dataset(csv_bytes([employee()], columns), name="current", rules=rules)


def test_missing_optional_column_is_added_with_a_note(rules):
    columns = [column for column in EXPECTED_COLUMNS if column != "bonus"]

    loaded = load_dataset(csv_bytes([employee()], columns), name="current", rules=rules)

    assert "bonus" in loaded.frame.columns
    assert loaded.frame.loc[0, "bonus"] is None
    assert any("bonus" in note for note in loaded.notes)


def test_extra_columns_are_kept_and_noted(rules):
    columns = list(EXPECTED_COLUMNS) + ["cost_center"]

    loaded = load_dataset(
        csv_bytes([employee(cost_center="CC-1")], columns), name="current", rules=rules
    )

    assert loaded.frame.loc[0, "cost_center"] == "CC-1"
    assert any("cost_center" in note for note in loaded.notes)


def test_semicolon_delimiter_is_detected(rules):
    raw = b"employee_id;first_name;last_name;contract_type;monthly_salary\nEMP-1;Ada;Rossi;full_time;2000\n"

    loaded = load_dataset(raw, name="current", rules=rules)

    assert loaded.frame.loc[0, "last_name"] == "Rossi"
    assert loaded.frame.loc[0, "monthly_salary"] == "2000"


def test_non_utf8_file_is_decoded_with_a_note(rules):
    text = "employee_id,first_name,last_name,contract_type,monthly_salary\nEMP-1,Zoë,Müller,full_time,2000\n"

    loaded = load_dataset(text.encode("cp1252"), name="current", rules=rules)

    assert loaded.frame.loc[0, "last_name"] == "Müller"
    assert any("cp1252" in note for note in loaded.notes)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"], ids=["LF", "CRLF", "CR"])
def test_every_line_ending_gives_the_same_rows_and_line_numbers(rules, newline):
    """CR-only files come from older Mac spreadsheet exports; they used to fail to parse."""
    lines = [
        b"employee_id,first_name,last_name,contract_type,monthly_salary",
        b"EMP-1,Ada,Rossi,full_time,2000",
        b'EMP-2,"Bea',  # a quoted field spanning two physical lines
        b'Maria",Bianchi,full_time,2000',
        b"EMP-3,Cyrus",
    ]
    loaded = load_dataset(newline.join(lines) + newline, name="current", rules=rules)

    assert list(loaded.frame["employee_id"]) == ["EMP-1", "EMP-2"]
    assert loaded.frame.loc[1, "first_name"].replace("\r\n", "\n").replace("\r", "\n") == "Bea\nMaria"
    assert list(loaded.frame[SOURCE_ROW]) == [2, 4]
    assert [issue.row_number for issue in loaded.issues] == [5]


def test_utf8_bom_is_ignored(rules):
    raw = "﻿employee_id,first_name,last_name,contract_type,monthly_salary\nEMP-1,Ada,Rossi,full_time,2000\n"

    loaded = load_dataset(raw.encode("utf-8"), name="current", rules=rules)

    assert "employee_id" in loaded.frame.columns


def test_row_with_wrong_field_count_is_skipped_and_reported(rules):
    raw = (
        b"employee_id,first_name,last_name,contract_type,monthly_salary\n"
        b"EMP-1,Ada,Rossi,full_time,2000\n"
        b"EMP-2,Bea,Bianchi,full_time,2000,EXTRA\n"
        b"EMP-3,Cyrus,Conti,full_time,2000\n"
    )

    loaded = load_dataset(raw, name="current", rules=rules)

    assert list(loaded.frame["employee_id"]) == ["EMP-1", "EMP-3"]
    assert len(loaded.issues) == 1
    issue = loaded.issues[0]
    assert issue.rule == "malformed_row"
    assert issue.row_number == 3
    assert issue.employee_id is None
    assert "skipped" in issue.message


def test_blank_lines_are_ignored(rules):
    raw = (
        b"employee_id,first_name,last_name,contract_type,monthly_salary\n"
        b"EMP-1,Ada,Rossi,full_time,2000\n"
        b"\n"
        b",,,,\n"
        b"EMP-2,Bea,Bianchi,full_time,2000\n"
    )

    loaded = load_dataset(raw, name="current", rules=rules)

    assert list(loaded.frame["employee_id"]) == ["EMP-1", "EMP-2"]
    assert list(loaded.frame[SOURCE_ROW]) == [2, 5]
    assert loaded.issues == []


def test_quoted_fields_with_commas_are_handled(rules):
    raw = (
        b"employee_id,first_name,last_name,contract_type,monthly_salary,department\n"
        b'EMP-1,Ada,Rossi,full_time,2000,"Sales, EMEA"\n'
    )

    loaded = load_dataset(raw, name="current", rules=rules)

    assert loaded.frame.loc[0, "department"] == "Sales, EMEA"


def test_loads_from_a_path(tmp_path, rules):
    path = tmp_path / "current.csv"
    path.write_bytes(csv_bytes([employee()]))

    loaded = load_dataset(path, name="current", rules=rules)

    assert loaded.record_count == 1


def test_missing_path_gives_a_clean_error(tmp_path, rules):
    with pytest.raises(DatasetLoadError, match="File not found"):
        load_dataset(tmp_path / "nope.csv", name="current", rules=rules)
