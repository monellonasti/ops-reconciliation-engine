"""Shared fixtures: a rules object and small builders for synthetic CSV datasets."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable, Sequence

import pytest

from src.config import Rules, load_rules
from src.loader import LoadedDataset, load_dataset
from src.models import EXPECTED_COLUMNS

# One well-formed synthetic record. Tests override only the fields they care about.
BASE_RECORD = {
    "employee_id": "EMP-00001",
    "first_name": "Ada",
    "last_name": "Rossi",
    "email": "ada.rossi@example.com",
    "iban": "IT60X0542811101000000123456",
    "contract_type": "full_time",
    "department": "Operations",
    "working_hours": "40",
    "monthly_salary": "2100",
    "bonus": "0",
    "overtime_hours": "4",
    "start_date": "2020-01-15",
    "end_date": "",
}


def employee(**overrides: object) -> dict[str, object]:
    record = dict(BASE_RECORD)
    record.update(overrides)
    return record


def csv_bytes(rows: Iterable[dict[str, object]], columns: Sequence[str] = EXPECTED_COLUMNS) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue().encode("utf-8")


@pytest.fixture(autouse=True)
def default_presentation():
    """Every test starts in English with the default number and date formats."""
    from src.i18n import set_language
    from src.utils import reset_formats

    set_language("en")
    reset_formats()
    yield
    set_language("en")
    reset_formats()


@pytest.fixture(scope="session")
def rules() -> Rules:
    return load_rules()


@pytest.fixture
def make_loaded(rules: Rules) -> Callable[..., LoadedDataset]:
    def _make(rows: Iterable[dict[str, object]], name: str = "current") -> LoadedDataset:
        return load_dataset(csv_bytes(rows), name=name, rules=rules)  # type: ignore[arg-type]

    return _make
