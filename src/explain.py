"""Explain a finding to an operator: what changed, why it was flagged, what to check.

Explanations are built from templates, so the application works with no
external services. If an Anthropic API key is configured *and* the optional
``anthropic`` package is installed, a natural-language rewrite can be
requested for one issue at a time. The model never decides whether a change
is legitimate; it only rephrases a finding the engine has already made.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from collections.abc import Callable

from pydantic import BaseModel

from src.config import Rules
from src.models import Issue, Severity
from src.utils import format_value

logger = logging.getLogger(__name__)

API_KEY_ENV = "ANTHROPIC_API_KEY"
MODEL_ENV = "OPS_RECON_LLM_MODEL"
DEFAULT_MODEL = "claude-opus-5"


class Explanation(BaseModel):
    what_changed: str
    why_flagged: str
    rule_triggered: str
    suggested_actions: list[str]

    def as_text(self) -> str:
        actions = "\n".join(f"- {action}" for action in self.suggested_actions)
        return (
            f"What changed: {self.what_changed}\n"
            f"Why it was flagged: {self.why_flagged}\n"
            f"Rule triggered: {self.rule_triggered}\n"
            f"Suggested checks:\n{actions}"
        )


# --- deterministic templates -------------------------------------------------------


def explain_issue(issue: Issue, rules: Rules) -> Explanation:
    builder = _BUILDERS.get(issue.rule, _generic)
    return builder(issue, rules)


def _salary_change(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.salary_change
    change = issue.change_percentage
    if change is None:
        why = (
            "The previous value was zero or missing, so a percentage cannot be computed. "
            "Any change from an empty baseline is surfaced for a human to confirm."
        )
    elif issue.severity is Severity.CRITICAL:
        why = f"A {abs(change):.2f}% change exceeds the configured {cfg.critical_percentage:g}% critical threshold."
    elif issue.severity is Severity.WARNING:
        why = (
            f"A {abs(change):.2f}% change exceeds the {cfg.warning_percentage:g}% warning threshold "
            f"but stays below the {cfg.critical_percentage:g}% critical threshold."
        )
    else:
        why = f"A {abs(change):.2f}% change is within the {cfg.warning_percentage:g}% tolerance; listed for completeness."

    actions = (
        ["No action required unless the change is unexpected for this employee."]
        if issue.severity is Severity.INFO
        else [
            "Verify whether a contractual change was approved and by whom.",
            "Verify the effective date of the change.",
            "Determine whether the change is permanent or a one-off adjustment.",
        ]
    )
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=(
            f"salary_change (warning above {cfg.warning_percentage:g}%, "
            f"critical above {cfg.critical_percentage:g}%)"
        ),
        suggested_actions=actions,
    )


def _iban_change(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.iban_change
    return Explanation(
        what_changed=issue.message,
        why_flagged=(
            "Bank details are a sensitive field. The engine treats every IBAN change as "
            f"{cfg.severity.value} and never decides on its own whether it is legitimate."
        ),
        rule_triggered=f"iban_change (severity {cfg.severity.value}, requires review: {cfg.requires_review})",
        suggested_actions=[
            "Confirm the change request came through the approved channel and matches a signed instruction.",
            "Verify the account holder of the new IBAN is the employee.",
            "Check whether the previous IBAN was used in the last cycle and whether a payment is pending.",
        ],
    )


def _new_record(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged="The employee_id does not exist in the previous cycle.",
        rule_triggered=f"lifecycle.new_record (severity {rules.lifecycle.new_record.severity.value})",
        suggested_actions=[
            "Confirm onboarding is complete in the source system.",
            "Check the record is not an existing employee re-entered under a new ID.",
        ],
    )


def _removed_record(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged="The employee_id exists in the previous cycle but not in the current export.",
        rule_triggered=f"lifecycle.removed_record (severity {rules.lifecycle.removed_record.severity.value})",
        suggested_actions=[
            "Confirm the leaver was processed and an end date was recorded in the source system.",
            "Check whether the record was dropped by an export filter rather than a real exit.",
        ],
    )


def _date_change(issue: Issue, rules: Rules) -> Explanation:
    outcome = getattr(rules.lifecycle, issue.rule)
    return Explanation(
        what_changed=issue.message,
        why_flagged="Employment dates drive eligibility and timing; a change is surfaced for confirmation.",
        rule_triggered=f"lifecycle.{issue.rule} (severity {outcome.severity.value})",
        suggested_actions=[
            "Confirm the new date against the signed contract or termination notice.",
            "Check whether related fields (contract type, hours, salary) should have changed too.",
        ],
    )


def _contract_change(issue: Issue, rules: Rules) -> Explanation:
    outcome = getattr(rules.contract_changes, issue.field or "contract_type")
    actions = {
        "contract_type": [
            "Confirm the contract amendment was signed and its effective date.",
            "Check that working hours and salary are consistent with the new contract type.",
        ],
        "working_hours": [
            "Confirm the change in hours was agreed and from which date.",
            "Check whether the salary was adjusted proportionally.",
        ],
        "department": [
            "Confirm the transfer with the receiving manager.",
            "Check cost-centre or approval mappings that depend on the department.",
        ],
    }[issue.field or "contract_type"]
    return Explanation(
        what_changed=issue.message,
        why_flagged=f"{issue.field} differs between the two cycles.",
        rule_triggered=f"contract_changes.{issue.field} (severity {outcome.severity.value})",
        suggested_actions=actions,
    )


def _duplicate(issue: Issue, rules: Rules) -> Explanation:
    field = issue.field or "employee_id"
    severity = getattr(rules.duplicates, field)
    if field == "employee_id":
        why = "The record key must be unique; two rows with the same ID cannot be matched reliably."
        actions = [
            "Identify which row is authoritative and remove or merge the other at source.",
            "Check whether the export joined a table that produced multiple rows per employee.",
        ]
    else:
        why = f"Two different records share the same {field}, which usually indicates a data-entry or export error."
        actions = [
            f"Check which employee the {field} really belongs to and correct the other record.",
            "Confirm the two records are not the same person entered twice.",
        ]
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=f"duplicates.{field} (severity {severity.value})",
        suggested_actions=actions,
    )


def _missing(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=f"{issue.field} is listed in required_fields; the record cannot be processed without it.",
        rule_triggered=f"required_fields / missing_data (severity {rules.missing_data.severity.value})",
        suggested_actions=[
            "Obtain the missing value from the source system and re-export.",
            "Decide whether the record can be processed this cycle without it.",
        ],
    )


def _invalid(issue: Issue, rules: Rules) -> Explanation:
    reasons = {
        "invalid_number": "The value could not be read as a number.",
        "invalid_date": f"The value is not a real date in the expected format ({rules.date_format}).",
        "negative_salary": "A monthly salary cannot be negative.",
        "end_before_start": "An employment cannot end before it starts.",
        "malformed_email": "The email address does not follow the expected pattern.",
        "malformed_row": "The line has a different number of fields than the header, so it could not be read.",
    }
    severity = (
        rules.invalid_values.malformed_email_severity
        if issue.rule == "malformed_email"
        else rules.invalid_values.severity
    )
    return Explanation(
        what_changed=issue.message,
        why_flagged=reasons.get(issue.rule, "The value cannot be right."),
        rule_triggered=f"invalid_values.{issue.rule} (severity {severity.value})",
        suggested_actions=[
            "Correct the value in the source system and re-export.",
            "Check whether the same error affects other rows of the export.",
        ],
    )


def _bonus(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.bonus
    return Explanation(
        what_changed=issue.message,
        why_flagged=(
            f"Bonuses above {cfg.warning_salary_ratio:.0%} of monthly salary are warnings and above "
            f"{cfg.critical_salary_ratio:.0%} are critical."
        ),
        rule_triggered=f"bonus (warning ratio {cfg.warning_salary_ratio:g}, critical ratio {cfg.critical_salary_ratio:g})",
        suggested_actions=[
            "Confirm the bonus amount was approved for this cycle.",
            "Check for unit mistakes, for example an annual amount entered as monthly.",
        ],
    )


def _overtime(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.overtime
    value = issue.current_value if issue.current_value is not None else issue.previous_value
    negative = isinstance(value, (int, float)) and value < cfg.minimum_hours
    return Explanation(
        what_changed=issue.message,
        why_flagged=(
            "Negative overtime is not a possible value and points to a data-entry error."
            if negative
            else f"Overtime above {format_value(cfg.warning_hours)} hours is a warning and above "
            f"{format_value(cfg.critical_hours)} hours is critical."
        ),
        rule_triggered=(
            f"overtime (minimum {cfg.minimum_hours:g}, warning above {cfg.warning_hours:g}, "
            f"critical above {cfg.critical_hours:g})"
        ),
        suggested_actions=[
            "Verify the hours against the timesheet or time-tracking system.",
            "Check for data-entry errors such as a wrong sign or a misplaced digit.",
        ],
    )


def _generic(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=f"Rule {issue.rule} fired with severity {issue.severity.value}.",
        rule_triggered=issue.rule,
        suggested_actions=["Review the record against the source system."],
    )


_BUILDERS: dict[str, Callable[[Issue, Rules], Explanation]] = {
    "salary_change": _salary_change,
    "iban_change": _iban_change,
    "new_record": _new_record,
    "removed_record": _removed_record,
    "start_date_changed": _date_change,
    "end_date_added": _date_change,
    "end_date_changed": _date_change,
    "contract_type_change": _contract_change,
    "working_hours_change": _contract_change,
    "department_change": _contract_change,
    "duplicate_employee_id": _duplicate,
    "duplicate_email": _duplicate,
    "duplicate_iban": _duplicate,
    "missing_required_field": _missing,
    "invalid_number": _invalid,
    "invalid_date": _invalid,
    "negative_salary": _invalid,
    "end_before_start": _invalid,
    "malformed_email": _invalid,
    "malformed_row": _invalid,
    "bonus_ratio": _bonus,
    "overtime_hours": _overtime,
}


# --- optional natural-language rewrite -----------------------------------------------

_SYSTEM_PROMPT = """You write short explanations for an operations reviewer.
You receive one finding produced by a deterministic reconciliation engine, together with the
rule configuration and a template explanation. Restate what changed and why the rule fired in
plain language, then list two or three concrete checks the reviewer could perform.

Rules you must follow:
- Never say or imply whether the change is legitimate, approved, correct or suspicious.
- Never invent facts, names, dates or amounts that are not in the input.
- Do not repeat masked values in any expanded form.
- Keep the whole answer under 120 words. Plain text, no headings."""


def llm_available() -> bool:
    """True when an API key is set and the optional SDK is installed."""
    return bool(os.environ.get(API_KEY_ENV)) and importlib.util.find_spec("anthropic") is not None


def explain_with_llm(issue: Issue, rules: Rules, explanation: Explanation | None = None) -> str:
    """Natural-language version of a finding, or a short reason why it is unavailable.

    Never raises: any API problem is returned as a one-line message so the UI
    can show it without a stack trace.
    """
    if not llm_available():
        return "AI explanation unavailable: set ANTHROPIC_API_KEY and install the anthropic package."

    import anthropic  # imported lazily so the package stays optional

    explanation = explanation or explain_issue(issue, rules)
    payload = {
        "finding": issue.model_dump(mode="json"),
        "template_explanation": explanation.model_dump(),
    }
    try:
        response = anthropic.Anthropic().messages.create(
            model=os.environ.get(MODEL_ENV, DEFAULT_MODEL),
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
        )
    except anthropic.AuthenticationError:
        return "AI explanation unavailable: the API key was rejected."
    except anthropic.RateLimitError:
        return "AI explanation unavailable: rate limited, try again in a moment."
    except anthropic.APIStatusError as exc:
        logger.warning("LLM explanation failed with status %s", exc.status_code)
        return f"AI explanation unavailable: the API returned status {exc.status_code}."
    except anthropic.APIConnectionError:
        return "AI explanation unavailable: could not reach the API."

    if response.stop_reason == "refusal":
        return "AI explanation unavailable for this finding; the template explanation applies."
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or "AI explanation unavailable: the model returned no text."
