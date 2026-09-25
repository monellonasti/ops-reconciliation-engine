"""The SQL examples run against the demo data and agree with the Python engine."""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pandas as pd
import pytest

from src.config import REPO_ROOT
from src.models import NUMERIC_FIELDS

SQL_DIR = REPO_ROOT / "sql"
DATA_DIR = REPO_ROOT / "data"


def load_table(connection: sqlite3.Connection, name: str, path) -> None:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="skip")
    for column in NUMERIC_FIELDS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.to_sql(name, connection, index=False)


def statements(path) -> list[str]:
    """Individual SELECT statements of a file, with comment lines removed."""
    code = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")
    )
    return [part.strip() for part in code.split(";") if part.strip()]


@pytest.fixture(scope="module")
def db():
    connection = sqlite3.connect(":memory:")
    load_table(connection, "employees_previous", DATA_DIR / "demo_previous.csv")
    load_table(connection, "employees_current", DATA_DIR / "demo_current.csv")
    yield connection
    connection.close()


def run(db, filename: str) -> list[pd.DataFrame]:
    return [pd.read_sql_query(statement, db) for statement in statements(SQL_DIR / filename)]


def test_every_sql_file_parses_and_runs(db):
    for path in sorted(SQL_DIR.glob("*.sql")):
        for statement in statements(path):
            pd.read_sql_query(statement, db)


def test_duplicates_sql(db):
    keys, emails, ibans = run(db, "duplicates.sql")

    assert list(keys["employee_id"]) == ["EMP-00064"]
    assert keys.loc[0, "occurrences"] == 2
    assert len(emails) == 1 and set(emails.loc[0, "employee_ids"].split(",")) == {"EMP-00019", "EMP-00183"}
    assert ibans.empty  # the only repeated IBAN belongs to the same duplicated record


def test_missing_records_sql(db):
    new, removed, keyless = run(db, "missing_records.sql")

    assert list(new["employee_id"]) == ["EMP-00201", "EMP-00202", "EMP-00203", "EMP-00204"]
    assert list(removed["employee_id"]) == ["EMP-00017", "EMP-00088", "EMP-00143"]
    assert len(keyless) == 1


def test_monthly_changes_sql(db):
    salaries, contract, ibans, leavers = run(db, "monthly_changes.sql")

    headline = salaries[salaries["employee_id"] == "EMP-00125"].iloc[0]
    assert headline["change_pct"] == 42.86 and headline["severity"] == "critical"
    assert salaries.iloc[0]["employee_id"] == "EMP-00150"  # largest change first

    changed = set(zip(contract["employee_id"], contract["field"]))
    assert {("EMP-00034", "contract_type"), ("EMP-00034", "working_hours"),
            ("EMP-00147", "contract_type"), ("EMP-00108", "working_hours"),
            ("EMP-00012", "department"), ("EMP-00119", "department")} <= changed

    assert sorted(ibans["employee_id"]) == ["EMP-00023", "EMP-00158"]
    assert ibans["previous_iban_masked"].str.contains(r"\*\*\*\*").all()
    assert ibans["current_iban_masked"].str.len().eq(13).all()

    assert sorted(leavers["employee_id"]) == ["EMP-00045", "EMP-00172", "EMP-00188"]


def test_anomalies_sql(db):
    missing, bonus, overtime, impossible = run(db, "anomalies.sql")

    assert {("EMP-00071", "last_name"), ("EMP-00093", "monthly_salary"),
            ("EMP-00203", "contract_type")} <= set(zip(missing["employee_id"], missing["missing_field"]))
    assert dict(zip(bonus["employee_id"], bonus["severity"])) == {"EMP-00176": "critical", "EMP-00029": "warning"}
    assert dict(zip(overtime["employee_id"], overtime["severity"])) == {
        "EMP-00081": "critical", "EMP-00050": "warning", "EMP-00164": "critical",
    }
    assert set(zip(impossible["employee_id"], impossible["problem"])) == {
        ("EMP-00056", "malformed_email"), ("EMP-00188", "end_before_start"),
    }


def test_short_bank_values_are_fully_masked():
    with closing(sqlite3.connect(":memory:")) as connection:
        load_table(connection, "employees_previous", DATA_DIR / "demo_previous.csv")
        load_table(connection, "employees_current", DATA_DIR / "demo_current.csv")
        connection.execute("UPDATE employees_current SET iban = 'SECRET' WHERE employee_id IN ('EMP-00001', 'EMP-00002')")
        duplicates = run(connection, "duplicates.sql")[2]
        assert "****" in set(duplicates.iban_masked)
        changes = run(connection, "monthly_changes.sql")[2]
        assert "SECRET" not in changes.to_csv(index=False)
