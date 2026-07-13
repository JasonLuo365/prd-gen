from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.session import SessionState


def state():
    return SessionState(session_id="test", mode="root", current_phase="P3", completed_phases=[], draft_content={})


def test_requirements_require_atomic_current_clauses():
    phase = RequirementsPhase(state())
    data = {"functional": [{"id": "REQ-001", "text": "x", "priority": "Must Have", "release_scope": "current", "requirement_kind": "aggregate"}], "non_functional": [{"id": "NFR-001", "text": "y", "release_scope": "current", "requirement_kind": "atomic"}]}
    met, message = phase.check_minimum_standard(data)
    assert not met
    assert "原子化" in message


def test_requirements_accept_explicit_exclusion():
    phase = RequirementsPhase(state())
    data = {"functional": [{"id": "REQ-001", "text": "x", "priority": "Could Have", "release_scope": "out_of_version", "scope_reason": "v2", "requirement_kind": "atomic"}], "non_functional": [{"id": "NFR-001", "text": "y", "release_scope": "current", "requirement_kind": "atomic"}]}
    assert phase.check_minimum_standard(data)[0]


def test_metrics_require_stable_id_and_numeric_target():
    phase = SuccessMetricsPhase(state())
    assert not phase.check_minimum_standard({"metrics": [{"id": "METRIC-001", "name": "latency", "target": "fast"}]})[0]
    assert phase.check_minimum_standard({"metrics": [{"id": "METRIC-001", "name": "latency", "target": "<= 3s"}]})[0]
