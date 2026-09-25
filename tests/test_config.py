"""Rules loading: defaults, validation of the YAML and the review policy."""

from __future__ import annotations

import pytest

from src import config
from src.config import RuleOutcome, Rules, RulesConfigError, load_rules, rules_from_dict
from src.models import Severity


def test_repository_rules_file_loads_with_expected_thresholds():
    rules = load_rules()

    assert rules.salary_change.warning_percentage == 15
    assert rules.salary_change.critical_percentage == 30
    assert rules.bonus.warning_salary_ratio == 0.5
    assert rules.bonus.critical_salary_ratio == 1.0
    assert rules.overtime.warning_hours == 60
    assert rules.overtime.critical_hours == 100
    assert rules.iban_change.severity is Severity.CRITICAL
    assert rules.iban_change.requires_review is True
    assert rules.duplicates.employee_id is Severity.CRITICAL
    assert rules.required_fields == [
        "employee_id", "first_name", "last_name", "contract_type", "monthly_salary",
    ]


def test_defaults_match_the_repository_file():
    assert Rules().model_dump() == load_rules().model_dump()


def test_missing_default_file_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_RULES_PATH", tmp_path / "absent.yaml")

    assert load_rules() == Rules()


def test_explicit_missing_file_is_an_error(tmp_path):
    with pytest.raises(RulesConfigError, match="not found"):
        load_rules(tmp_path / "absent.yaml")


def test_invalid_yaml_is_reported_cleanly(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("salary_change: [unclosed", encoding="utf-8")

    with pytest.raises(RulesConfigError, match="not valid YAML"):
        load_rules(path)


def test_unknown_keys_are_rejected_to_catch_typos():
    with pytest.raises(RulesConfigError, match="salary_change.warning_percent"):
        rules_from_dict({"salary_change": {"warning_percent": 15}})


def test_inverted_thresholds_are_rejected():
    with pytest.raises(RulesConfigError, match="warning_percentage must be below"):
        rules_from_dict({"salary_change": {"warning_percentage": 40, "critical_percentage": 30}})
    with pytest.raises(RulesConfigError, match="warning_salary_ratio"):
        rules_from_dict({"bonus": {"warning_salary_ratio": 1.5, "critical_salary_ratio": 1.0}})
    with pytest.raises(RulesConfigError, match="minimum_hours"):
        rules_from_dict({"overtime": {"minimum_hours": 10, "warning_hours": 5}})


def test_key_field_is_always_required():
    rules = rules_from_dict({"required_fields": ["first_name"]})

    assert rules.required_fields == ["employee_id", "first_name"]


def test_partial_file_keeps_defaults_for_the_rest():
    rules = rules_from_dict({"overtime": {"warning_hours": 40}})

    assert rules.overtime.warning_hours == 40
    assert rules.overtime.critical_hours == 100
    assert rules.salary_change.critical_percentage == 30


def test_review_policy_and_overrides():
    rules = Rules()

    assert rules.requires_review(Severity.INFO) is False
    assert rules.requires_review(Severity.WARNING) is True
    assert rules.requires_review(Severity.CRITICAL) is True
    assert rules.requires_review(Severity.CRITICAL, override=False) is False
    assert rules.outcome_requires_review(RuleOutcome(severity=Severity.INFO, requires_review=True))
    assert rules.outcome_requires_review(RuleOutcome(severity=Severity.WARNING)) is True
