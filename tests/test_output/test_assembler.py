from prd_flow.output.assembler import assemble_prd


def test_assemble_prd_emits_oracle_contract_not_gherkin():
    contract = {"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "actor": "user", "preconditions": ["ready"], "trigger": "query", "response": ["ranked products"], "observable_oracles": ["order shown"], "boundaries": ["empty history -> profile fallback"], "exceptions": ["API down -> message"], "evidence_refs": ["owner"]}
    text = assemble_prd({
        "P1": {"doc_id": "TEST", "release_scope_frozen": True, "agent_review_passed": True},
        "P3": {"functional": [{"id": "REQ-001", "text": "rank products", "priority": "Must Have"}], "non_functional": []},
        "P4": {"contracts": [contract]},
    })
    assert "ready_for_test_generation: true" in text.lower()
    assert "# Acceptance Contracts" in text
    assert "AC-001" in text
    assert "```gherkin" not in text


def test_assemble_prd_marks_missing_oracle_not_ready():
    text = assemble_prd({"P1": {"doc_id": "TEST", "release_scope_frozen": True, "agent_review_passed": True}, "P3": {"functional": [{"id": "REQ-001", "text": "x", "priority": "Could Have"}], "non_functional": []}})
    assert "ready_for_test_generation: false" in text.lower()
    assert "oracle_blocked_count: 1" in text
