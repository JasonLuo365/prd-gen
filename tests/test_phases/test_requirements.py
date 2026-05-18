from unittest.mock import patch

from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.session import SessionState


def test_requirements_phase_collects_data():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    result = phase.collect(
        functional=[
            {"id": "REQ-001", "text": "支持邮箱注册", "priority": "Must Have", "gherkin_count": 2},
        ],
        non_functional=[
            {"id": "NFR-001", "text": "可用性 ≥ 99.9%"},
        ],
    )

    assert len(result["functional"]) == 1
    assert result["functional"][0]["id"] == "REQ-001"
    assert result["functional"][0]["priority"] == "Must Have"
    assert result["functional"][0]["gherkin_count"] == 2
    assert len(result["non_functional"]) == 1
    assert result["non_functional"][0]["id"] == "NFR-001"
    assert state.draft_content["P3"] == result
    assert "P3" in state.completed_phases


def test_requirements_phase_run_interactive():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    inputs = [
        "REQ-001", "支持邮箱注册", "Must Have", "2",
        "done",
        "NFR-001", "可用性 ≥ 99.9%",
        "done",
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["functional"]) == 1
    assert result["functional"][0]["id"] == "REQ-001"
    assert len(result["non_functional"]) == 1
    assert result["non_functional"][0]["id"] == "NFR-001"
