"""Load business rules from YAML into a validated, typed object.

Application code receives a :class:`Rules` instance and reads thresholds from
it. The defaults below mirror ``rules/validation_rules.yaml`` so the engine
still behaves sensibly if a key is omitted from the file.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.i18n import available_languages
from src.models import KEY_FIELD, Severity

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = REPO_ROOT / "rules" / "validation_rules.yaml"
RULES_PATH_ENV = "OPS_RECON_RULES"


class RulesConfigError(Exception):
    """Raised when the rules file cannot be read or does not make sense."""


class _StrictModel(BaseModel):
    # Reject unknown keys so a typo in the YAML fails loudly instead of silently
    # falling back to a default.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RuleOutcome(_StrictModel):
    """What happens when a rule fires: how severe it is and whether a human must look."""

    severity: Severity
    requires_review: bool | None = Field(
        default=None, description="Explicit override; None means follow review_policy."
    )


class MissingDataRules(_StrictModel):
    severity: Severity = Severity.CRITICAL


class InvalidValueRules(_StrictModel):
    severity: Severity = Severity.CRITICAL
    malformed_email_severity: Severity = Severity.WARNING


class DuplicateRules(_StrictModel):
    employee_id: Literal[Severity.CRITICAL] = Severity.CRITICAL
    email: Severity = Severity.WARNING
    iban: Severity = Severity.WARNING


class SalaryChangeRules(_StrictModel):
    warning_percentage: float = 15.0
    critical_percentage: float = 30.0

    @model_validator(mode="after")
    def _ordered(self) -> SalaryChangeRules:
        if not 0 <= self.warning_percentage < self.critical_percentage:
            raise ValueError("warning_percentage must be below critical_percentage")
        return self


class BonusRules(_StrictModel):
    warning_salary_ratio: float = 0.5
    critical_salary_ratio: float = 1.0

    @model_validator(mode="after")
    def _ordered(self) -> BonusRules:
        if not 0 <= self.warning_salary_ratio < self.critical_salary_ratio:
            raise ValueError("warning_salary_ratio must be below critical_salary_ratio")
        return self


class OvertimeRules(_StrictModel):
    minimum_hours: float = 0.0
    warning_hours: float = 60.0
    critical_hours: float = 100.0

    @model_validator(mode="after")
    def _ordered(self) -> OvertimeRules:
        if not self.minimum_hours <= self.warning_hours < self.critical_hours:
            raise ValueError("expected minimum_hours <= warning_hours < critical_hours")
        return self


class IbanChangeRules(_StrictModel):
    requires_review: Literal[True] = True
    severity: Literal[Severity.CRITICAL] = Severity.CRITICAL


class ContractChangeRules(_StrictModel):
    contract_type: RuleOutcome = RuleOutcome(severity=Severity.WARNING)
    working_hours: RuleOutcome = RuleOutcome(severity=Severity.WARNING)
    department: RuleOutcome = RuleOutcome(severity=Severity.INFO)


class LifecycleRules(_StrictModel):
    new_record: RuleOutcome = RuleOutcome(severity=Severity.INFO)
    removed_record: RuleOutcome = RuleOutcome(severity=Severity.WARNING)
    start_date_changed: RuleOutcome = RuleOutcome(severity=Severity.WARNING)
    end_date_added: RuleOutcome = RuleOutcome(severity=Severity.WARNING)
    end_date_changed: RuleOutcome = RuleOutcome(severity=Severity.WARNING)


class ExpectedChangeRules(_StrictModel):
    """An approved change that did not happen is a finding with this severity."""

    missing_severity: Severity = Severity.WARNING


class HistoryRules(_StrictModel):
    """Where operator decisions are kept between runs. Nothing is written until one is saved."""

    enabled: bool = True
    path: str = "history/review_history.sqlite"


class FormatRules(_StrictModel):
    """How numbers and dates are written in the input files and shown to people.

    The defaults read ``2,100.50`` and ``2024-09-30``; the Italian profile uses
    ``2.100,50`` and ``30/09/2024``. Dates are tried in the listed order.
    """

    input_date_formats: list[str] = Field(default_factory=lambda: ["%Y-%m-%d", "%d/%m/%Y"])
    output_date_format: str = "%Y-%m-%d"
    decimal_separator: str = "."
    thousands_separator: str = ","

    @model_validator(mode="after")
    def _consistent(self) -> FormatRules:
        if self.decimal_separator not in (".", ","):
            raise ValueError("decimal_separator must be '.' or ','")
        if self.thousands_separator not in ("", ".", ",", "'", " "):
            raise ValueError("thousands_separator must be '.', ',', an apostrophe, a space or empty")
        if self.thousands_separator == self.decimal_separator:
            raise ValueError("decimal_separator and thousands_separator must differ")
        if not self.input_date_formats:
            raise ValueError("input_date_formats must list at least one format")
        for pattern in [*self.input_date_formats, self.output_date_format]:
            try:
                datetime(2024, 1, 31).strftime(pattern)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid date format '{pattern}'") from exc
        return self


class Rules(_StrictModel):
    language: str = "en"
    required_fields: list[str] = Field(
        default_factory=lambda: [
            "employee_id",
            "first_name",
            "last_name",
            "contract_type",
            "monthly_salary",
        ]
    )
    review_policy: dict[Severity, bool] = Field(
        default_factory=lambda: {
            Severity.INFO: False,
            Severity.WARNING: True,
            Severity.CRITICAL: True,
        }
    )
    missing_data: MissingDataRules = MissingDataRules()
    invalid_values: InvalidValueRules = InvalidValueRules()
    duplicates: DuplicateRules = DuplicateRules()
    salary_change: SalaryChangeRules = SalaryChangeRules()
    bonus: BonusRules = BonusRules()
    overtime: OvertimeRules = OvertimeRules()
    iban_change: IbanChangeRules = IbanChangeRules()
    contract_changes: ContractChangeRules = ContractChangeRules()
    lifecycle: LifecycleRules = LifecycleRules()
    masked_fields: list[str] = Field(default_factory=lambda: ["iban"])
    formats: FormatRules = FormatRules()
    history: HistoryRules = HistoryRules()
    expected_changes: ExpectedChangeRules = ExpectedChangeRules()

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        code = value.strip().lower()
        if code not in available_languages():
            raise ValueError(f"language must be one of {', '.join(available_languages())}")
        return code

    @model_validator(mode="after")
    def _key_always_required(self) -> Rules:
        if KEY_FIELD not in self.required_fields:
            self.required_fields.insert(0, KEY_FIELD)
        if "iban" not in self.masked_fields:
            self.masked_fields.append("iban")
        if KEY_FIELD in self.masked_fields:
            raise ValueError("employee_id cannot be masked: it identifies review records")
        return self

    def requires_review(self, severity: Severity, override: bool | None = None) -> bool:
        """Decide whether an issue lands in the review queue."""
        if override is not None:
            return override
        return self.review_policy.get(severity, severity != Severity.INFO)

    def outcome_requires_review(self, outcome: RuleOutcome) -> bool:
        return self.requires_review(outcome.severity, outcome.requires_review)


def default_rules_path() -> Path:
    """The rules file to use when none is given: ``OPS_RECON_RULES`` if set, else the repository default."""
    override = os.environ.get(RULES_PATH_ENV)
    if override:
        path = Path(override)
        return path if path.is_absolute() else REPO_ROOT / path
    return DEFAULT_RULES_PATH


def load_rules(path: str | Path | None = None) -> Rules:
    """Read the YAML rules file.

    With ``path=None`` the file named by ``OPS_RECON_RULES`` is used, or the
    repository default; if the repository default is missing the built-in
    defaults apply. An explicit or environment-selected path that does not
    exist is an error.
    """
    rules_path = Path(path) if path is not None else default_rules_path()
    if not rules_path.exists():
        if path is None and rules_path == DEFAULT_RULES_PATH:
            return Rules()
        raise RulesConfigError(f"Rules file not found: {rules_path}")

    try:
        raw = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulesConfigError(f"Rules file is not valid YAML ({rules_path.name}).") from exc
    except (OSError, UnicodeError) as exc:
        raise RulesConfigError("Rules file could not be read as UTF-8.") from exc

    return rules_from_dict({} if raw is None else raw, source=rules_path.name)


def rules_from_dict(raw: dict, source: str = "rules") -> Rules:
    """Build :class:`Rules` from a plain mapping, turning validation errors into one message."""
    if not isinstance(raw, dict):
        raise RulesConfigError(f"{source}: expected a mapping at the top level")
    try:
        return Rules.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise RulesConfigError(f"{source}: {problems}") from exc
