"""Load business rules from YAML into a validated, typed object.

Application code receives a :class:`Rules` instance and reads thresholds from
it. The defaults below mirror ``rules/validation_rules.yaml`` so the engine
still behaves sensibly if a key is omitted from the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.models import KEY_FIELD, Severity

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = REPO_ROOT / "rules" / "validation_rules.yaml"


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


class Rules(_StrictModel):
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
    date_format: str = "%Y-%m-%d"

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


def load_rules(path: str | Path | None = None) -> Rules:
    """Read the YAML rules file.

    With ``path=None`` the repository default is used; if that file is missing the
    built-in defaults apply. An explicit path that does not exist is an error.
    """
    rules_path = Path(path) if path is not None else DEFAULT_RULES_PATH
    if not rules_path.exists():
        if path is None:
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
