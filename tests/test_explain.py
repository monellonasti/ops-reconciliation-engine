"""Explanations: deterministic templates for every rule, and the optional LLM gate."""

from __future__ import annotations

import importlib.machinery
import sys
import types

import pytest

from src import explain as explain_module
from src.config import REPO_ROOT
from src.engine import reconcile_sources
from src.explain import explain_issue, explain_with_llm, llm_available
from src.models import Category, Issue, Severity


def make_issue(**overrides) -> Issue:
    base = dict(
        employee_id="EMP-00125",
        dataset="both",
        category=Category.SALARY_CHANGE,
        field="monthly_salary",
        previous_value=2100.0,
        current_value=3000.0,
        change_percentage=42.86,
        rule="salary_change",
        severity=Severity.CRITICAL,
        requires_review=True,
        message="Monthly salary increased by 42.86% (from 2,100 to 3,000).",
    )
    base.update(overrides)
    return Issue(**base)


def test_every_rule_the_engine_emits_has_a_dedicated_template(rules):
    result = reconcile_sources(
        REPO_ROOT / "data" / "demo_previous.csv", REPO_ROOT / "data" / "demo_current.csv", rules
    )
    emitted = {issue.rule for issue in result.issues}

    assert emitted <= set(explain_module._BUILDERS), "generic fallback would be used"
    for issue in result.issues:
        explanation = explain_issue(issue, rules)
        assert explanation.what_changed and explanation.why_flagged
        assert explanation.rule_triggered and explanation.suggested_actions


def test_critical_salary_explanation_matches_the_brief(rules):
    explanation = explain_issue(make_issue(), rules)

    assert "increased by 42.86%" in explanation.what_changed
    assert "exceeds the configured 30% critical threshold" in explanation.why_flagged
    assert explanation.rule_triggered == "salary_change (warning above 15%, critical above 30%)"
    assert explanation.suggested_actions == [
        "Verify whether a contractual change was approved and by whom.",
        "Verify the effective date of the change.",
        "Determine whether the change is permanent or a one-off adjustment.",
    ]


def test_warning_and_info_salary_explanations_name_the_thresholds(rules):
    warning = explain_issue(make_issue(change_percentage=20.0, severity=Severity.WARNING), rules)
    info = explain_issue(
        make_issue(change_percentage=5.0, severity=Severity.INFO, requires_review=False), rules
    )

    assert "15% warning threshold" in warning.why_flagged and "30% critical" in warning.why_flagged
    assert "within the 15% tolerance" in info.why_flagged
    assert info.suggested_actions == ["No action required unless the change is unexpected for this employee."]


def test_salary_without_percentage_explains_why(rules):
    explanation = explain_issue(
        make_issue(previous_value=0.0, change_percentage=None, severity=Severity.WARNING), rules
    )

    assert "percentage cannot be computed" in explanation.why_flagged


def test_iban_explanation_keeps_values_masked(rules):
    issue = make_issue(
        category=Category.IBAN_CHANGE, field="iban", rule="iban_change",
        previous_value="IT60X****3456", current_value="DE893****3000", change_percentage=None,
        message="IBAN changed from IT60X****3456 to DE893****3000.",
    )

    explanation = explain_issue(issue, rules)

    assert "****" in explanation.what_changed
    assert "never decides" in explanation.why_flagged
    assert "critical" in explanation.rule_triggered


def test_explanation_as_text_is_readable(rules):
    text = explain_issue(make_issue(), rules).as_text()

    assert text.startswith("What changed: Monthly salary increased")
    assert "Suggested checks:\n- Verify whether" in text


def test_unknown_rule_falls_back_to_a_generic_explanation(rules):
    explanation = explain_issue(make_issue(rule="something_new"), rules)

    assert explanation.rule_triggered == "something_new"
    assert explanation.suggested_actions


# --- optional LLM ------------------------------------------------------------------------


def test_llm_is_off_without_an_api_key(monkeypatch, rules):
    monkeypatch.delenv(explain_module.API_KEY_ENV, raising=False)

    assert llm_available() is False
    assert explain_with_llm(make_issue(), rules).startswith("AI explanation unavailable")


def test_llm_is_off_when_the_package_is_missing(monkeypatch, rules):
    monkeypatch.setenv(explain_module.API_KEY_ENV, "test-key")
    monkeypatch.setattr(explain_module.importlib.util, "find_spec", lambda name: None)

    assert llm_available() is False


@pytest.fixture
def fake_anthropic(monkeypatch):
    """A stand-in for the SDK so the request/response handling can be exercised offline."""
    module = types.ModuleType("anthropic")
    module.__spec__ = importlib.machinery.ModuleSpec("anthropic", None)
    for name in ("AuthenticationError", "RateLimitError", "APIConnectionError"):
        setattr(module, name, type(name, (Exception,), {}))
    module.APIStatusError = type("APIStatusError", (Exception,), {"status_code": 500})
    calls: list[dict] = []

    class Messages:
        def __init__(self, response):
            self.response = response

        def create(self, **kwargs):
            calls.append(kwargs)
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    def install(response):
        module.Anthropic = lambda: types.SimpleNamespace(messages=Messages(response))
        monkeypatch.setitem(sys.modules, "anthropic", module)
        monkeypatch.setenv(explain_module.API_KEY_ENV, "test-key")

    return types.SimpleNamespace(module=module, install=install, calls=calls)


def test_llm_rewrite_returns_the_text_blocks(fake_anthropic, rules):
    response = types.SimpleNamespace(
        stop_reason="end_turn",
        content=[
            types.SimpleNamespace(type="thinking", text="ignored"),
            types.SimpleNamespace(type="text", text="The salary rose by 42.86%. Checks: ..."),
        ],
    )
    fake_anthropic.install(response)

    text = explain_with_llm(make_issue(), rules)

    call = fake_anthropic.calls[0]
    assert text == "The salary rose by 42.86%. Checks: ..."
    assert call["model"] == explain_module.DEFAULT_MODEL
    assert "never say or imply whether the change is legitimate" in call["system"].lower()
    assert "42.86" in call["messages"][0]["content"]


def test_llm_refusal_falls_back_to_the_template(fake_anthropic, rules):
    fake_anthropic.install(types.SimpleNamespace(stop_reason="refusal", content=[]))

    text = explain_with_llm(make_issue(), rules)

    assert "template explanation applies" in text


def test_llm_errors_become_one_line_messages(fake_anthropic, rules):
    errors = fake_anthropic.module

    fake_anthropic.install(errors.AuthenticationError())
    assert "API key was rejected" in explain_with_llm(make_issue(), rules)

    fake_anthropic.install(errors.APIConnectionError())
    assert "could not reach" in explain_with_llm(make_issue(), rules)

    fake_anthropic.install(errors.APIStatusError())
    assert "status 500" in explain_with_llm(make_issue(), rules)


def test_unexpected_llm_failure_is_private(fake_anthropic, rules, caplog):
    fake_anthropic.install(RuntimeError("PrivateValue"))
    assert "template explanation applies" in explain_with_llm(make_issue(), rules)
    assert "PrivateValue" not in caplog.text
