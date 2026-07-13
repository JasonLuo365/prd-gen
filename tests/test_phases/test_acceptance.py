from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.session import SessionState


def state():
    return SessionState(session_id="test", mode="root", current_phase="P4", completed_phases=[], draft_content={
        "P3": {"functional": [{"id": "REQ-001", "priority": "Should Have", "release_scope": "current"}], "non_functional": []}
    })


def contract():
    return {"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "release_scope": "current", "actor": "user", "preconditions": ["signed in"], "trigger": "submits query", "response": ["ranked products"], "observable_oracles": ["order displayed"], "boundaries": ["empty target history -> cross-domain profile"], "exceptions": ["API unavailable -> failure displayed"], "evidence_refs": ["owner-1"]}


def test_acceptance_phase_collects_contracts():
    phase = AcceptancePhase(state())
    result = phase.collect([contract()])
    assert result == {"contracts": [contract()]}


def test_acceptance_phase_requires_all_current_priorities():
    phase = AcceptancePhase(state())
    met, message = phase.check_minimum_standard({"contracts": []})
    assert not met
    assert "REQ-001" in message


def test_acceptance_phase_passes_complete_contract():
    phase = AcceptancePhase(state())
    met, _ = phase.check_minimum_standard({"contracts": [contract()]})
    assert met
