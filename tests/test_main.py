from prd_flow.main import _check_oracle_coverage, _run_smart_check
from prd_flow.quality.smart_req import SMARTResult
from prd_flow.quality.suggest import suggest_fix
from prd_flow.session import SessionState


def state(contracts=None):
    return SessionState(session_id="x", mode="root", current_phase="P4", completed_phases=[], draft_content={
        "P3": {"functional": [{"id": "REQ-001", "text": "系统展示推荐结果", "priority": "Could Have"}], "non_functional": []},
        "P4": {"contracts": contracts or []},
    })


def contract():
    return {"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "actor": "user", "preconditions": ["ready"], "trigger": "query", "response": ["results"], "observable_oracles": ["shown"], "boundaries": ["empty -> fallback"], "exceptions": ["failure -> message"], "evidence_refs": ["owner"]}


def test_main_oracle_gate_covers_could_have():
    assert _check_oracle_coverage(state())[0]["id"] == "REQ-001"
    assert _check_oracle_coverage(state([contract()])) == []


def test_smart_check_uses_contract_coverage_when_available():
    assert not _run_smart_check(state())[0].testable
    assert _run_smart_check(state([contract()]))[0].testable


def test_fix_suggestion_requests_acceptance_contract_not_gherkin():
    result = SMARTResult(req_id="REQ-001", specific=True, measurable=True, testable=False)
    fix = suggest_fix({}, result)
    assert "Acceptance Contract" in fix
    assert "Gherkin" not in fix
