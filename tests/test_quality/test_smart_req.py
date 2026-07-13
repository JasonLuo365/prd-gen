from prd_flow.quality.smart_req import check_smart_req


def complete_contract():
    return {"id": "AC-1", "type": "functional", "verifies": ["REQ-001"], "actor": "user", "preconditions": ["ready"], "trigger": "query", "response": ["results"], "observable_oracles": ["shown"], "boundaries": ["empty -> empty"], "exceptions": ["failure -> message"], "evidence_refs": ["owner"]}


def test_smart_req_testability_uses_acceptance_contract_not_gherkin_count():
    req = {"id": "REQ-001", "text": "系统展示推荐结果", "priority": "Should Have", "gherkin_count": 10}
    assert not check_smart_req(req, []).testable
    assert check_smart_req(req, [complete_contract()]).testable


def test_smart_req_flags_vague_language():
    result = check_smart_req({"id": "REQ-1", "text": "系统应该很快"})
    assert not result.specific
    assert not result.measurable
