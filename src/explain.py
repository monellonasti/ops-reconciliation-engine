"""Explain a finding to an operator: what changed, why it was flagged, what to check.

Explanations are built from templates in the configured language, so the
application works with no external services. If an Anthropic API key is
configured *and* the optional ``anthropic`` package is installed, a
natural-language rewrite can be requested for one issue at a time. The model
never decides whether a change is legitimate; it only rephrases a finding the
engine has already made.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from collections.abc import Callable

from pydantic import BaseModel

from src.config import Rules
from src.i18n import t, t_list
from src.models import Issue, Severity
from src.utils import format_change, format_plain, format_value, redact_iban_text

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
        return t(
            "explain.text",
            what=self.what_changed,
            why=self.why_flagged,
            rule=self.rule_triggered,
            actions=actions,
        )


# --- deterministic templates -------------------------------------------------------


def explain_issue(issue: Issue, rules: Rules) -> Explanation:
    builder = _BUILDERS.get(issue.rule, _generic)
    explanation = builder(issue, rules)
    if issue.rule == "expected_change_missing":
        return explanation
    if issue.expected_reference is not None:
        return _with_expectation_matched(explanation, issue)
    if issue.expected_mismatch is not None:
        return _with_expectation_mismatch(explanation, issue)
    return explanation


def _with_expectation_matched(explanation: Explanation, issue: Issue) -> Explanation:
    if issue.rule == "iban_change":
        why = t("explain.expectation.iban_why", why=explanation.why_flagged, reference=issue.expected_reference)
        actions = t_list("explain.expectation.iban_actions")
    else:
        why = t(
            "explain.expectation.matched_why",
            reference=issue.expected_reference,
            why=explanation.why_flagged,
        )
        actions = t_list("explain.expectation.matched_actions")
    return explanation.model_copy(update={"why_flagged": why, "suggested_actions": actions})


def _with_expectation_mismatch(explanation: Explanation, issue: Issue) -> Explanation:
    why = t("explain.expectation.mismatch_why", why=explanation.why_flagged, expected=issue.expected_mismatch)
    actions = [t("explain.expectation.mismatch_action"), *explanation.suggested_actions]
    return explanation.model_copy(update={"why_flagged": why, "suggested_actions": actions})


def _expected_missing(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.expected_missing.why"),
        rule_triggered=t(
            "explain.expected_missing.rule", severity=rules.expected_changes.missing_severity.value
        ),
        suggested_actions=t_list("explain.expected_missing.actions"),
    )


def _salary_change(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.salary_change
    change = issue.change_percentage
    warning, critical = format_plain(cfg.warning_percentage), format_plain(cfg.critical_percentage)
    shown = "" if change is None else format_change(change, (cfg.warning_percentage, cfg.critical_percentage))
    if change is None:
        why = t("explain.salary.why_no_pct")
    elif issue.severity is Severity.CRITICAL:
        why = t("explain.salary.why_critical", pct=shown, critical=critical)
    elif issue.severity is Severity.WARNING:
        why = t("explain.salary.why_warning", pct=shown, warning=warning, critical=critical)
    else:
        why = t("explain.salary.why_info", pct=shown, warning=warning)

    actions = t_list("explain.salary.actions_info" if issue.severity is Severity.INFO else "explain.salary.actions")
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=t("explain.salary.rule", warning=warning, critical=critical),
        suggested_actions=actions,
    )


def _iban_change(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.iban_change
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.iban.why", severity=cfg.severity.value),
        rule_triggered=t("explain.iban.rule", severity=cfg.severity.value, review=cfg.requires_review),
        suggested_actions=t_list("explain.iban.actions"),
    )


def _new_record(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.new.why"),
        rule_triggered=t("explain.new.rule", severity=rules.lifecycle.new_record.severity.value),
        suggested_actions=t_list("explain.new.actions"),
    )


def _removed_record(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.removed.why"),
        rule_triggered=t("explain.removed.rule", severity=rules.lifecycle.removed_record.severity.value),
        suggested_actions=t_list("explain.removed.actions"),
    )


def _date_change(issue: Issue, rules: Rules) -> Explanation:
    outcome = getattr(rules.lifecycle, issue.rule)
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.date.why"),
        rule_triggered=t("explain.date.rule", rule=issue.rule, severity=outcome.severity.value),
        suggested_actions=t_list("explain.date.actions"),
    )


def _contract_change(issue: Issue, rules: Rules) -> Explanation:
    field = issue.field or "contract_type"
    outcome = getattr(rules.contract_changes, field)
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.contract.why", field=field),
        rule_triggered=t("explain.contract.rule", field=field, severity=outcome.severity.value),
        suggested_actions=t_list(f"explain.contract.actions.{field}"),
    )


def _duplicate(issue: Issue, rules: Rules) -> Explanation:
    field = issue.field or "employee_id"
    severity = getattr(rules.duplicates, field)
    if field == "employee_id":
        why = t("explain.duplicate.key_why")
        actions = t_list("explain.duplicate.key_actions")
    else:
        why = t("explain.duplicate.value_why", field=field)
        actions = [
            t("explain.duplicate.value_action", field=field),
            t("explain.duplicate.value_action_2"),
        ]
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=t("explain.duplicate.rule", field=field, severity=severity.value),
        suggested_actions=actions,
    )


def _missing(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.missing.why", field=issue.field),
        rule_triggered=t("explain.missing.rule", severity=rules.missing_data.severity.value),
        suggested_actions=t_list("explain.missing.actions"),
    )


def _invalid(issue: Issue, rules: Rules) -> Explanation:
    if issue.rule == "invalid_date":
        why = t("explain.invalid.invalid_date", formats=" / ".join(rules.formats.input_date_formats))
    elif issue.rule in {"invalid_number", "negative_salary", "end_before_start", "malformed_email", "malformed_row"}:
        why = t(f"explain.invalid.{issue.rule}")
    else:
        why = t("explain.invalid.fallback")
    severity = (
        rules.invalid_values.malformed_email_severity
        if issue.rule == "malformed_email"
        else rules.invalid_values.severity
    )
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=t("explain.invalid.rule", rule=issue.rule, severity=severity.value),
        suggested_actions=t_list("explain.invalid.actions"),
    )


def _bonus(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.bonus
    return Explanation(
        what_changed=issue.message,
        why_flagged=t(
            "explain.bonus.why",
            warning=f"{cfg.warning_salary_ratio:.0%}",
            critical=f"{cfg.critical_salary_ratio:.0%}",
        ),
        rule_triggered=t(
            "explain.bonus.rule",
            warning_ratio=format_plain(cfg.warning_salary_ratio),
            critical_ratio=format_plain(cfg.critical_salary_ratio),
        ),
        suggested_actions=t_list("explain.bonus.actions"),
    )


def _overtime(issue: Issue, rules: Rules) -> Explanation:
    cfg = rules.overtime
    value = issue.current_value if issue.current_value is not None else issue.previous_value
    negative = isinstance(value, (int, float)) and value < cfg.minimum_hours
    why = (
        t("explain.overtime.why_below", minimum=format_plain(cfg.minimum_hours))
        if negative
        else t(
            "explain.overtime.why_above",
            warning=format_value(cfg.warning_hours),
            critical=format_value(cfg.critical_hours),
        )
    )
    return Explanation(
        what_changed=issue.message,
        why_flagged=why,
        rule_triggered=t(
            "explain.overtime.rule",
            minimum=format_plain(cfg.minimum_hours),
            warning=format_plain(cfg.warning_hours),
            critical=format_plain(cfg.critical_hours),
        ),
        suggested_actions=t_list("explain.overtime.actions"),
    )


def _generic(issue: Issue, rules: Rules) -> Explanation:
    return Explanation(
        what_changed=issue.message,
        why_flagged=t("explain.generic.why", rule=issue.rule, severity=issue.severity.value),
        rule_triggered=issue.rule,
        suggested_actions=t_list("explain.generic.actions"),
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
    "expected_change_missing": _expected_missing,
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
        return t("ai.unavailable_setup")

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
            system=f"{_SYSTEM_PROMPT}\n- {t('ai.language_instruction')}",
            messages=[{"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)}],
        )
    except anthropic.AuthenticationError:
        return t("ai.unavailable_key")
    except anthropic.RateLimitError:
        return t("ai.unavailable_rate")
    except anthropic.APIStatusError as exc:
        logger.warning("LLM explanation failed with status %s", exc.status_code)
        return t("ai.unavailable_status", status=exc.status_code)
    except anthropic.APIConnectionError:
        return t("ai.unavailable_network")
    except Exception:
        logger.warning("AI explanation failed; error details omitted to protect input values")
        return t("ai.unavailable_failed")

    if response.stop_reason == "refusal":
        return t("ai.unavailable_refusal")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return redact_iban_text(text) or t("ai.unavailable_empty")
