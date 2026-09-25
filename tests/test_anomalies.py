"""Bonus and overtime anomaly rules, including exact threshold boundaries."""

from __future__ import annotations

import pytest

from src.anomaly_detection import bonus_severity, detect_anomalies, overtime_severity
from src.models import Category, Severity
from src.validators import validate_dataset
from tests.conftest import employee


def anomalies_for(make_loaded, rules, rows):
    return detect_anomalies(validate_dataset(make_loaded(rows, "current"), rules), rules)


# --- bonus ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bonus", "salary", "expected"),
    [
        (0, 2000, None),
        (1000, 2000, None),  # exactly 50% is not unusual
        (1001, 2000, Severity.WARNING),
        (2000, 2000, Severity.WARNING),  # exactly 100% stays a warning
        (2001, 2000, Severity.CRITICAL),
        (5000, 2000, Severity.CRITICAL),
        (None, 2000, None),
        (1500, None, None),  # missing salary is reported elsewhere
        (1500, 0, None),  # zero salary: ratio not meaningful
        (-100, 2000, None),
    ],
)
def test_bonus_thresholds(bonus, salary, expected, rules):
    assert bonus_severity(bonus, salary, rules) is expected


def test_bonus_anomaly_issue_explains_the_ratio(make_loaded, rules):
    issues = anomalies_for(make_loaded, rules, [employee(monthly_salary="2100", bonus="1500")])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.category is Category.BONUS_ANOMALY
    assert issue.rule == "bonus_ratio"
    assert issue.severity is Severity.WARNING
    assert issue.current_value == 1500.0
    assert "71.4%" in issue.message
    assert "50%" in issue.message


def test_critical_bonus_names_the_critical_threshold(make_loaded, rules):
    issues = anomalies_for(make_loaded, rules, [employee(monthly_salary="2000", bonus="3000")])

    assert issues[0].severity is Severity.CRITICAL
    assert "100%" in issues[0].message


# --- overtime --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (None, None),
        (0, None),
        (60, None),  # exactly 60 is fine
        (60.5, Severity.WARNING),
        (100, Severity.WARNING),  # exactly 100 stays a warning
        (100.5, Severity.CRITICAL),
        (-0.5, Severity.CRITICAL),
        (-40, Severity.CRITICAL),
    ],
)
def test_overtime_thresholds(hours, expected, rules):
    assert overtime_severity(hours, rules) is expected


def test_negative_overtime_message(make_loaded, rules):
    issues = anomalies_for(make_loaded, rules, [employee(overtime_hours="-5")])

    assert len(issues) == 1
    assert issues[0].category is Category.OVERTIME_ANOMALY
    assert issues[0].severity is Severity.CRITICAL
    assert "negative" in issues[0].message


def test_excessive_overtime_message_names_the_threshold(make_loaded, rules):
    issues = anomalies_for(make_loaded, rules, [employee(overtime_hours="72")])

    assert issues[0].severity is Severity.WARNING
    assert "60-hour" in issues[0].message


def test_normal_record_has_no_anomalies(make_loaded, rules):
    assert anomalies_for(make_loaded, rules, [employee(bonus="200", overtime_hours="12")]) == []
