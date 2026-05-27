"""Tests for phase minimum standard checks."""
import pytest

from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.phases.problem_statement import ProblemStatementPhase
from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.session import SessionState


def _make_state(mode="root"):
    return SessionState(
        session_id="test",
        mode=mode,
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )


# ---------------------------------------------------------------------------
# FrontmatterPhase
# ---------------------------------------------------------------------------
def test_frontmatter_missing_fields():
    state = _make_state()
    phase = FrontmatterPhase(state)
    data = {"doc_id": "TEST", "version": "1.0"}  # missing author, status, priority
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "缺少必填字段" in msg
    assert "author" in msg
    assert "status" in msg
    assert "priority" in msg


def test_frontmatter_empty_fields():
    state = _make_state()
    phase = FrontmatterPhase(state)
    data = {"doc_id": "TEST", "version": "1.0", "author": "", "status": "draft", "priority": "P0"}
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "author" in msg


def test_frontmatter_complete():
    state = _make_state()
    phase = FrontmatterPhase(state)
    data = {
        "doc_id": "TEST",
        "version": "1.0",
        "author": "A",
        "status": "draft",
        "priority": "P0",
    }
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Frontmatter 最低标准已满足" in msg


# ---------------------------------------------------------------------------
# ProblemStatementPhase
# ---------------------------------------------------------------------------
def test_problem_statement_missing():
    state = _make_state()
    phase = ProblemStatementPhase(state)
    data = {"target_users": "devs", "pain_points": "slow builds"}  # missing opportunity
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "缺少必填内容" in msg
    assert "opportunity" in msg


def test_problem_statement_empty():
    state = _make_state()
    phase = ProblemStatementPhase(state)
    data = {"target_users": "devs", "pain_points": "", "opportunity": "automation"}
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "pain_points" in msg


def test_problem_statement_complete():
    state = _make_state()
    phase = ProblemStatementPhase(state)
    data = {"target_users": "devs", "pain_points": "slow builds", "opportunity": "automation"}
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Problem Statement 最低标准已满足" in msg


# ---------------------------------------------------------------------------
# RequirementsPhase
# ---------------------------------------------------------------------------
def test_requirements_no_functional():
    state = _make_state()
    phase = RequirementsPhase(state)
    data = {"functional": [], "non_functional": [{"id": "NFR-001", "text": "secure"}]}
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "至少需要 1 条功能需求" in msg


def test_requirements_missing_priority():
    state = _make_state()
    phase = RequirementsPhase(state)
    data = {
        "functional": [
            {"id": "REQ-001", "text": "login", "priority": "Must Have"},
            {"id": "REQ-002", "text": "signup"},  # missing priority
        ],
        "non_functional": [{"id": "NFR-001", "text": "secure"}],
    }
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "以下需求缺少优先级" in msg
    assert "REQ-002" in msg


def test_requirements_missing_nfr():
    state = _make_state()
    phase = RequirementsPhase(state)
    data = {
        "functional": [{"id": "REQ-001", "text": "login", "priority": "Must Have"}],
        "non_functional": [],
    }
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "至少需要 1 条非功能需求" in msg


def test_requirements_complete():
    state = _make_state()
    phase = RequirementsPhase(state)
    data = {
        "functional": [{"id": "REQ-001", "text": "login", "priority": "Must Have"}],
        "non_functional": [{"id": "NFR-001", "text": "secure"}],
    }
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Requirements 最低标准已满足" in msg


# ---------------------------------------------------------------------------
# AcceptancePhase
# ---------------------------------------------------------------------------
def test_acceptance_uncovered_must_have():
    state = _make_state()
    state.draft_content["P3"] = {
        "functional": [
            {"id": "REQ-001", "text": "login", "priority": "Must Have"},
            {"id": "REQ-002", "text": "signup", "priority": "Must Have"},
        ],
        "non_functional": [],
    }
    phase = AcceptancePhase(state)
    # Only one scenario linked to REQ-001
    data = {
        "scenarios": [
            {"feature": "Auth", "scenario": "Login", "req_id": "REQ-001"},
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "以下 Must-Have 需求缺少 Gherkin 场景" in msg
    assert "REQ-002" in msg


def test_acceptance_complete():
    state = _make_state()
    state.draft_content["P3"] = {
        "functional": [
            {"id": "REQ-001", "text": "login", "priority": "Must Have"},
            {"id": "REQ-002", "text": "signup", "priority": "Should Have"},
        ],
        "non_functional": [],
    }
    phase = AcceptancePhase(state)
    data = {
        "scenarios": [
            {"feature": "Auth", "scenario": "Login", "req_id": "REQ-001"},
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Acceptance 最低标准已满足" in msg


def test_acceptance_no_must_have():
    state = _make_state()
    state.draft_content["P3"] = {
        "functional": [
            {"id": "REQ-001", "text": "login", "priority": "Should Have"},
        ],
        "non_functional": [],
    }
    phase = AcceptancePhase(state)
    data = {"scenarios": []}
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "无 Must-Have 需求" in msg


def test_acceptance_no_p3_data():
    state = _make_state()
    phase = AcceptancePhase(state)
    data = {"scenarios": []}
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "无 Must-Have 需求" in msg


# ---------------------------------------------------------------------------
# SuccessMetricsPhase
# ---------------------------------------------------------------------------
def test_metrics_none():
    state = _make_state()
    phase = SuccessMetricsPhase(state)
    data = {"metrics": []}
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "至少需要 1 个成功指标" in msg


def test_metrics_not_measurable():
    state = _make_state()
    phase = SuccessMetricsPhase(state)
    data = {
        "metrics": [
            {"name": "uptime", "target": "high"},  # no number / symbol
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "指标 'uptime' 的目标值不包含可量化数值" in msg


def test_metrics_complete_with_number():
    state = _make_state()
    phase = SuccessMetricsPhase(state)
    data = {
        "metrics": [
            {"name": "uptime", "target": "99.9%"},
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Success Metrics 最低标准已满足" in msg


def test_metrics_complete_with_symbol():
    state = _make_state()
    phase = SuccessMetricsPhase(state)
    data = {
        "metrics": [
            {"name": "latency", "target": "≤ 200ms"},
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert met is True
    assert "Success Metrics 最低标准已满足" in msg


def test_metrics_partial_measurable():
    state = _make_state()
    phase = SuccessMetricsPhase(state)
    data = {
        "metrics": [
            {"name": "uptime", "target": "99.9%"},
            {"name": "adoption", "target": "better"},  # not measurable
        ]
    }
    met, msg = phase.check_minimum_standard(data)
    assert not met
    assert "指标 'adoption' 的目标值不包含可量化数值" in msg
