"""Single-cycle anomaly rules on the current dataset: unusual bonus and overtime values.

These are not comparisons with the previous cycle; they flag values that look
wrong on their own. Thresholds come from the rules file.
"""

from __future__ import annotations

from typing import Any

from src.config import Rules
from src.models import Category, Issue, Severity
from src.utils import format_value, is_missing
from src.validators import IssueFactory, ValidatedDataset


def detect_anomalies(current: ValidatedDataset, rules: Rules) -> list[Issue]:
    factory = IssueFactory(current.name, rules)
    issues: list[Issue] = []
    for row in current.frame.to_dict("records"):
        issues += check_bonus(row, factory, rules)
        issues += check_overtime(row, factory, rules)
    return issues


# --- bonus ---------------------------------------------------------------------


def bonus_severity(bonus: Any, salary: Any, rules: Rules) -> Severity | None:
    """Severity for a bonus relative to monthly salary, or None when nothing is unusual."""
    if is_missing(bonus) or is_missing(salary) or salary <= 0 or bonus <= 0:
        return None
    ratio = bonus / salary
    if ratio > rules.bonus.critical_salary_ratio:
        return Severity.CRITICAL
    if ratio > rules.bonus.warning_salary_ratio:
        return Severity.WARNING
    return None


def check_bonus(row: dict[str, Any], factory: IssueFactory, rules: Rules) -> list[Issue]:
    bonus, salary = row.get("bonus"), row.get("monthly_salary")
    severity = bonus_severity(bonus, salary, rules)
    if severity is None:
        return []
    ratio = bonus / salary * 100
    threshold = (
        rules.bonus.critical_salary_ratio
        if severity is Severity.CRITICAL
        else rules.bonus.warning_salary_ratio
    )
    return [
        factory.issue(
            row,
            category=Category.BONUS_ANOMALY,
            field="bonus",
            rule="bonus_ratio",
            severity=severity,
            value=bonus,
            message=(
                f"Bonus {format_value(bonus)} is {ratio:.1f}% of monthly salary "
                f"{format_value(salary)} (threshold {threshold:.0%})."
            ),
        )
    ]


# --- overtime --------------------------------------------------------------------


def overtime_severity(hours: Any, rules: Rules) -> Severity | None:
    if is_missing(hours):
        return None
    if hours < rules.overtime.minimum_hours:
        return Severity.CRITICAL
    if hours > rules.overtime.critical_hours:
        return Severity.CRITICAL
    if hours > rules.overtime.warning_hours:
        return Severity.WARNING
    return None


def check_overtime(row: dict[str, Any], factory: IssueFactory, rules: Rules) -> list[Issue]:
    hours = row.get("overtime_hours")
    severity = overtime_severity(hours, rules)
    if severity is None:
        return []
    if hours < rules.overtime.minimum_hours:
        message = f"Overtime hours are negative ({format_value(hours)})."
    else:
        limit = (
            rules.overtime.critical_hours
            if severity is Severity.CRITICAL
            else rules.overtime.warning_hours
        )
        message = f"Overtime of {format_value(hours)} hours exceeds the {format_value(limit)}-hour threshold."
    return [
        factory.issue(
            row,
            category=Category.OVERTIME_ANOMALY,
            field="overtime_hours",
            rule="overtime_hours",
            severity=severity,
            value=hours,
            message=message,
        )
    ]
