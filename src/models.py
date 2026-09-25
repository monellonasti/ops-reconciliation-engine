"""Typed models shared by every stage of the engine.

The central object is :class:`Issue`. Every check in the engine, whether it
runs on one dataset or compares two, produces a list of issues with the same
shape. The UI, the exports and the tests all consume that single model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.utils import redact_iban_text

# Column layout of the demo use case. The key field is what records are matched on.
KEY_FIELD = "employee_id"
TEXT_FIELDS = (
    "employee_id",
    "first_name",
    "last_name",
    "email",
    "iban",
    "contract_type",
    "department",
)
NUMERIC_FIELDS = ("working_hours", "monthly_salary", "bonus", "overtime_hours")
DATE_FIELDS = ("start_date", "end_date")
EXPECTED_COLUMNS = TEXT_FIELDS + NUMERIC_FIELDS + DATE_FIELDS

# Internal column added by the loader: the 1-based line number in the source file.
SOURCE_ROW = "source_row"

DatasetName = Literal["previous", "current", "both"]


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "critical": 2}[self.value]


class Category(StrEnum):
    LIFECYCLE = "lifecycle"
    DUPLICATE = "duplicate"
    MISSING_DATA = "missing_data"
    INVALID_VALUE = "invalid_value"
    SALARY_CHANGE = "salary_change"
    IBAN_CHANGE = "iban_change"
    CONTRACT_CHANGE = "contract_change"
    BONUS_ANOMALY = "bonus_anomaly"
    OVERTIME_ANOMALY = "overtime_anomaly"

    @property
    def label(self) -> str:
        return {
            "lifecycle": "Lifecycle",
            "duplicate": "Duplicate",
            "missing_data": "Missing data",
            "invalid_value": "Invalid value",
            "salary_change": "Salary change",
            "iban_change": "IBAN change",
            "contract_change": "Contract change",
            "bonus_anomaly": "Bonus anomaly",
            "overtime_anomaly": "Overtime anomaly",
        }[self.value]


class Issue(BaseModel):
    """One finding about one record.

    Values stored here are already safe to display: masked fields (IBAN) are
    masked before the issue is created, so nothing downstream has to remember
    to do it.
    """

    model_config = ConfigDict(frozen=True)

    employee_id: str | None = None
    row_number: int | None = Field(
        default=None, description="Source line number, used when the record has no key."
    )
    dataset: DatasetName
    category: Category
    field: str | None = None
    previous_value: str | float | None = None
    current_value: str | float | None = None
    change_percentage: float | None = None
    rule: str
    severity: Severity
    requires_review: bool
    message: str

    @field_validator("employee_id", "field", "previous_value", "current_value", "message")
    @classmethod
    def _sanitize_text(cls, value):
        return redact_iban_text(value) if isinstance(value, str) else value

    @property
    def record_label(self) -> str:
        if self.employee_id:
            return self.employee_id
        if self.row_number is not None:
            return f"row {self.row_number}"
        return "unknown record"


class Summary(BaseModel):
    previous_records: int
    current_records: int
    new_records: int
    removed_records: int
    critical_issues: int
    warnings: int
    info: int
    changes_detected: int
    records_requiring_review: int

    @property
    def total_issues(self) -> int:
        return self.critical_issues + self.warnings + self.info


class ReconciliationResult(BaseModel):
    issues: list[Issue]
    summary: Summary
    notes: list[str] = Field(
        default_factory=list,
        description="Non-blocking remarks about the input files, e.g. optional columns absent.",
    )

    @property
    def review_queue(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.requires_review]
