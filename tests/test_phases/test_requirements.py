from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.session import SessionState


def test_collect_defaults_release_scope_and_atomic_kind():
    state = SessionState(session_id="x", mode="root", current_phase="P3", completed_phases=[], draft_content={})
    result = RequirementsPhase(state).collect(
        [{"id": "REQ-001", "text": "rank products", "priority": "Must Have"}],
        [{"id": "NFR-001", "text": "p95 <= 3s"}],
    )
    assert result["functional"][0]["release_scope"] == "current"
    assert result["functional"][0]["requirement_kind"] == "atomic"
    assert result["non_functional"][0]["requirement_kind"] == "atomic"
    assert "gherkin_count" not in result["functional"][0]
