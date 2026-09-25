"""The shipped demo datasets exercise every category and stay in sync with the generator."""

from __future__ import annotations

import importlib.util

import pytest

from src.config import REPO_ROOT
from src.engine import reconcile_sources
from src.models import Category, Severity

DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(scope="module")
def demo_result(rules):
    return reconcile_sources(DATA_DIR / "demo_previous.csv", DATA_DIR / "demo_current.csv", rules)


def test_demo_covers_every_category(demo_result):
    assert {issue.category for issue in demo_result.issues} == set(Category)
    assert {issue.severity for issue in demo_result.issues} == set(Severity)


def test_demo_headline_scenario_matches_the_brief(demo_result):
    issue = next(
        i for i in demo_result.issues if i.employee_id == "EMP-00125" and i.rule == "salary_change"
    )

    assert issue.previous_value == 2100.0
    assert issue.current_value == 3000.0
    assert issue.change_percentage == pytest.approx(42.857143)
    assert issue.severity is Severity.CRITICAL


def test_demo_summary_is_stable(demo_result):
    summary = demo_result.summary

    assert summary.previous_records == 200
    assert summary.current_records == 203
    assert summary.new_records == 4
    assert summary.removed_records == 3
    assert summary.critical_issues > 0 and summary.warnings > 0 and summary.info > 0
    assert summary.records_requiring_review > 0


def test_demo_files_never_leak_a_full_iban_into_issues(demo_result):
    text = "\n".join(issue.model_dump_json() for issue in demo_result.issues)

    assert "****" in text
    assert not any(len(token) == 27 and token.startswith("IT") for token in text.replace('"', " ").split())


def test_generator_is_deterministic(tmp_path):
    script = REPO_ROOT / "scripts" / "generate_demo_data.py"
    previous = (DATA_DIR / "demo_previous.csv").read_bytes()
    current = (DATA_DIR / "demo_current.csv").read_bytes()

    spec = importlib.util.spec_from_file_location("demo_generator", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DATA_DIR = tmp_path
    module.main()

    assert (tmp_path / "demo_previous.csv").read_bytes() == previous
    assert (tmp_path / "demo_current.csv").read_bytes() == current
