"""Language catalogs, configurable number/date formats and the Italian rules profile."""

from __future__ import annotations

import re
import string

import pandas as pd
import pytest

from src import i18n
from src.config import REPO_ROOT, Rules, RulesConfigError, load_rules, rules_from_dict
from src.engine import reconcile_sources
from src.explain import explain_issue
from src.history import ReviewHistory
from src.i18n import en, it, set_language, t, t_list
from src.models import Category, ReviewStatus, Severity
from src.utils import (
    configure_formats,
    format_change,
    format_for_display,
    format_number,
    format_percentage,
    format_value,
    parse_number,
)
from tests.conftest import csv_bytes, employee

ITALIAN_RULES = REPO_ROOT / "rules" / "validation_rules.it.yaml"


def italian_rules() -> Rules:
    return load_rules(ITALIAN_RULES)


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


# --- catalogs ------------------------------------------------------------------------


def test_catalogs_have_the_same_keys_and_placeholders():
    assert set(en.MESSAGES) == set(it.MESSAGES)
    for key, english in en.MESSAGES.items():
        italian = it.MESSAGES[key]
        assert type(english) is type(italian), key
        if isinstance(english, str):
            assert placeholders(english) == placeholders(italian), key
        else:
            assert len(english) == len(italian), key


def test_no_catalog_value_is_empty():
    for catalog in (en.MESSAGES, it.MESSAGES):
        for key, value in catalog.items():
            entries = [value] if isinstance(value, str) else list(value)
            assert all(entry.strip() for entry in entries), key


def test_t_uses_the_active_language_and_falls_back_to_english(monkeypatch):
    assert t("severity.warning") == "Warning"
    set_language("it")
    assert t("severity.warning") == "Avviso"
    assert t("record.row", line=7) == "riga 7"
    monkeypatch.delitem(it.MESSAGES, "severity.warning")
    assert t("severity.warning") == "Warning"  # graceful fallback
    with pytest.raises(KeyError):
        t("no.such.key")
    with pytest.raises(ValueError):
        set_language("xx")
    assert i18n.available_languages() == ["en", "it"]


def test_placeholder_named_key_is_allowed():
    assert t("validators.duplicate_key", key="EMP-1", count=2, rows="2, 3") == (
        "employee_id EMP-1 appears 2 times (rows 2, 3)."
    )
    assert t_list("explain.salary.actions")[0].startswith("Verify whether")


def test_labels_follow_the_language():
    set_language("it")
    assert Category.IBAN_CHANGE.label == "Cambio IBAN"
    assert Severity.CRITICAL.label == "Critico"
    assert ReviewStatus.NEEDS_ACTION.label == "Da correggere"


# --- number parsing and formatting -------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2100", 2100.0),
        ("2,100", 2100.0),
        ("2,100.50", 2100.5),
        ("1,234,567.89", 1234567.89),
        ("-1,500", -1500.0),
        ("2100.5", 2100.5),
        ("1e3", 1000.0),
        ("2,1", None),  # not a thousands group
        ("2.100,50", None),  # Italian convention under the default formats
        ("abc", None),
        ("", None),
        (None, None),
        (2100, 2100.0),  # Excel numbers arrive typed
        (True, None),
    ],
)
def test_parse_number_default_formats(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2100", 2100.0),
        ("2.100", 2100.0),
        ("2.100,50", 2100.5),
        ("1.234.567,89", 1234567.89),
        ("2100,5", 2100.5),
        ("2,5", 2.5),
        ("2.5", None),  # misgrouped dot: rejected, not misread as 25
        ("2100.50", None),
        ("2,100", 2.1),  # a comma is the decimal separator in this convention
    ],
)
def test_parse_number_italian_formats(text, expected):
    configure_formats(decimal_separator=",", thousands_separator=".")
    assert parse_number(text) == expected


def test_formatting_follows_the_configured_separators():
    assert format_number(2100.5) == "2,100.50"
    assert format_value(2100.0) == "2,100"
    configure_formats(decimal_separator=",", thousands_separator=".", output_date_format="%d/%m/%Y")
    assert format_number(2100.5) == "2.100,50"
    assert format_value(1234567.0) == "1.234.567"
    assert format_percentage(42.857) == "+42,86%"
    assert format_change(15.0001, (15, 30)) == "15,0001"
    assert format_value(pd.Timestamp("2024-09-30")) == "30/09/2024"
    assert format_for_display("2024-09-30") == "30/09/2024"  # ISO strings stored in findings
    assert format_for_display(2100.0) == "2.100"
    assert format_for_display("full_time") == "full_time"


def test_no_thousands_separator_is_allowed():
    configure_formats(decimal_separator=",", thousands_separator="")
    assert parse_number("2100,5") == 2100.5
    assert parse_number("2.100") is None
    assert format_number(2100.5) == "2100,50"


# --- rules profile ---------------------------------------------------------------------


def test_italian_profile_differs_from_the_default_only_in_language_and_formats():
    default, italian = load_rules(), italian_rules()

    assert italian.language == "it"
    assert italian.formats.decimal_separator == ","
    assert italian.formats.thousands_separator == "."
    assert italian.formats.output_date_format == "%d/%m/%Y"
    assert italian.formats.input_date_formats[0] == "%d/%m/%Y"
    assert italian.model_dump(exclude={"language", "formats"}) == default.model_dump(exclude={"language", "formats"})


@pytest.mark.parametrize(
    "config",
    [
        {"language": "de"},
        {"formats": {"decimal_separator": ";"}},
        {"formats": {"decimal_separator": ",", "thousands_separator": ","}},
        {"formats": {"input_date_formats": []}},
        {"formats": {"output_date_format": "%Q"}},
    ],
)
def test_invalid_language_or_formats_are_rejected(config):
    with pytest.raises(RulesConfigError):
        rules_from_dict(config)


def test_rules_file_can_be_selected_with_an_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_RECON_RULES", "rules/validation_rules.it.yaml")
    assert load_rules().language == "it"

    monkeypatch.setenv("OPS_RECON_RULES", str(tmp_path / "missing.yaml"))
    with pytest.raises(RulesConfigError, match="not found"):
        load_rules()


# --- end to end in Italian -------------------------------------------------------------


ITALIAN_HEADER = "employee_id;first_name;last_name;email;iban;contract_type;department;working_hours;monthly_salary;bonus;overtime_hours;start_date;end_date\n"


def italian_csv(*rows: str) -> bytes:
    return (ITALIAN_HEADER + "".join(row + "\n" for row in rows)).encode("utf-8")


def test_italian_export_is_read_and_reported_in_italian():
    previous = italian_csv("EMP-00001;Ada;Rossi;ada@example.com;IT60X0542811101000000123456;full_time;Operations;40;2.100,00;0;4;15/01/2020;")
    current = italian_csv("EMP-00001;Ada;Rossi;ada@example.com;IT60X0542811101000000123456;full_time;Operations;40;3.000,50;1.600;72;15/01/2020;30/09/2024")

    result = reconcile_sources(previous, current, italian_rules())

    by_rule = {issue.rule: issue for issue in result.issues}
    salary = by_rule["salary_change"]
    assert salary.previous_value == 2100.0 and salary.current_value == 3000.5
    assert salary.severity is Severity.CRITICAL
    assert salary.message == "Retribuzione mensile aumentata del 42,88% (da 2.100 a 3.000,50)."
    assert by_rule["end_date_added"].message == "end_date aggiunta: 30/09/2024."
    assert by_rule["end_date_added"].current_value == "2024-09-30"  # stored canonically
    assert "straordinario" in by_rule["overtime_hours"].message.lower()
    assert "53,3%" in by_rule["bonus_ratio"].message  # 1.600 / 3.000,50
    assert any("Modifiche" in note or "Nota" in note for note in result.notes) or result.notes == []
    explanation = explain_issue(salary, italian_rules())
    assert "supera la soglia critica configurata del 30%" in explanation.why_flagged
    assert explanation.suggested_actions[0].startswith("Verificare")


def test_iso_file_under_the_italian_profile_flags_ambiguous_numbers_instead_of_misreading():
    current = italian_csv("EMP-00001;Ada;Rossi;ada@example.com;IT60X0542811101000000123456;full_time;Operations;40;2100.5;0;4;2020-01-15;")

    result = reconcile_sources(current, current, italian_rules())

    invalid = [issue for issue in result.issues if issue.rule == "invalid_number"]
    assert len(invalid) == 2  # previous and current cycle both carry the ambiguous value
    assert invalid[0].message == "monthly_salary ha un valore numerico non valido o non finito."


def test_fingerprints_do_not_depend_on_the_display_convention(tmp_path):
    history = ReviewHistory(tmp_path / "h.sqlite")
    previous = csv_bytes([employee(monthly_salary="2100", end_date="")])
    current = csv_bytes([employee(monthly_salary="3000", end_date="2024-09-30")])
    english = reconcile_sources(previous, current, Rules(), history)
    for issue in english.issues:
        history.record(issue, ReviewStatus.ACCEPTED)

    italian = reconcile_sources(previous, current, italian_rules(), history)

    assert {issue.rule for issue in italian.issues} == {"salary_change", "end_date_added"}
    assert all(issue.review_status is ReviewStatus.ACCEPTED for issue in italian.issues)


def test_english_is_restored_for_the_next_test():
    assert i18n.get_language() == "en"
    assert format_value(2100.5) == "2,100.50"
    assert not re.search(r"riga", t("record.row", line=1))
