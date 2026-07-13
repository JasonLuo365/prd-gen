from prd_flow.output.assembler import assemble_prd
from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.quality.oracle import check_oracle_coverage
from prd_flow.session import SessionState


def test_end_to_end_oracle_ready_prd_generation():
    state = SessionState(session_id="x", mode="root", current_phase="P3", completed_phases=[], draft_content={"P1": {"doc_id": "TEST", "release_scope_frozen": True, "agent_review_passed": True}})
    RequirementsPhase(state).collect(
        [{"id": "REQ-001", "text": "系统展示按偏好排序的亚马逊商品", "priority": "Should Have"}],
        [],
    )
    contract = {"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "actor": "user", "preconditions": ["history available"], "trigger": "asks for recommendation", "response": ["ranked Amazon products"], "observable_oracles": ["order displayed"], "boundaries": ["new domain -> cross-domain profile"], "exceptions": ["API failure -> failure shown"], "evidence_refs": ["owner"]}
    AcceptancePhase(state).collect([contract])
    assert check_oracle_coverage(state.draft_content["P3"], state.draft_content["P4"]["contracts"]) == []
    text = assemble_prd(state.draft_content)
    assert "ready_for_test_generation: true" in text.lower()
    assert "Scenario:" not in text


def test_missing_oracle_blocks_even_when_gherkin_count_exists():
    reqs = {"functional": [{"id": "REQ-001", "text": "x", "priority": "Must Have", "gherkin_count": 10}], "non_functional": []}
    assert check_oracle_coverage(reqs, [])[0]["id"] == "REQ-001"
