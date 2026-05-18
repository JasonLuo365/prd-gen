from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.session import SessionState


def test_frontmatter_phase_generates_metadata():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )
    phase = FrontmatterPhase(state)

    # Simulate user providing project info
    result = phase.collect(
        project_name="ecommerce_platform",
        author="team",
        priority="P0",
    )

    assert result["doc_id"] == "ECOMMERCE-PLATFORM-v1.0"
    assert result["layer"] == "root"
    assert result["parent_doc"] is None
    assert result["version"] == "1.0.0"
