from prd_flow.output.assembler import assemble_prd
from prd_flow.quality.oracle import check_oracle_coverage, validate_acceptance_contract


def functional_contract(req_id="REQ-001"):
    return {
        "id": "AC-REQ-001-01",
        "type": "functional",
        "verifies": [req_id],
        "release_scope": "current",
        "actor": "Amazon shopper",
        "preconditions": ["purchase history and reviews are available"],
        "trigger": "asks for a product recommendation",
        "response": ["rank Amazon products by query and profile fit"],
        "observable_oracles": ["ordered products include fit explanations"],
        "boundaries": ["no target-domain history -> use cross-domain stable profile"],
        "exceptions": ["Amazon API unavailable -> report retrieval failure"],
        "evidence_refs": ["owner-decision:recommendation-flow"],
    }


def nfr_contract():
    return {
        "id": "AC-NFR-001-01",
        "type": "nfr",
        "verifies": ["NFR-001"],
        "release_scope": "current",
        "population": "all recommendation queries in the evaluation set",
        "measurement_start": "query submitted",
        "measurement_end": "ranked list displayed",
        "unit": "ms",
        "threshold": "p95 <= 3000",
        "exclusions": ["Amazon API outage"],
        "pass_rule": "computed p95 is <= 3000 ms",
        "evidence_refs": ["owner-decision:latency"],
    }


def requirements():
    return {
        "functional": [
            {"id": "REQ-001", "text": "rank products", "priority": "Should Have", "release_scope": "current", "requirement_kind": "atomic"},
            {"id": "REQ-002", "text": "future feature", "priority": "Could Have", "release_scope": "out_of_version", "scope_reason": "v2", "requirement_kind": "atomic"},
        ],
        "non_functional": [
            {"id": "NFR-001", "text": "latency", "release_scope": "current", "requirement_kind": "atomic"},
        ],
    }


def test_current_should_requirement_is_oracle_bound():
    gaps = check_oracle_coverage(requirements(), [nfr_contract()])
    assert [gap["id"] for gap in gaps] == ["REQ-001"]


def test_complete_functional_and_nfr_contracts_are_ready():
    assert check_oracle_coverage(requirements(), [functional_contract(), nfr_contract()]) == []


def test_nfr_missing_population_is_blocked():
    contract = nfr_contract()
    contract["population"] = ""
    assert "missing population" in validate_acceptance_contract(contract)


def test_gherkin_count_does_not_satisfy_oracle_gate():
    data = requirements()
    data["functional"][0]["gherkin_count"] = 99
    gaps = check_oracle_coverage(data, [nfr_contract()])
    assert gaps[0]["id"] == "REQ-001"


def test_prd_output_contains_contracts_and_no_gherkin():
    text = assemble_prd({
        "P3": requirements(),
        "P4": {"contracts": [functional_contract(), nfr_contract()]},
        "P5": {"metrics": [{"id": "METRIC-001", "name": "latency", "target": "p95 <= 3000 ms", "method": "evaluation set", "verifies": ["NFR-001"]}]},
    })
    assert "# Acceptance Contracts" in text
    assert "| REQ-001 | functional | current | AC-REQ-001-01 | ready |" in text
    assert "```gherkin" not in text
    assert "Scenario:" not in text
