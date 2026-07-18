import json
from pathlib import Path

import pytest

from prd_flow.main import _canonical_hash, main


@pytest.mark.parametrize("domain,foreign", [
    ("inventory reservation", "device telemetry"),
    ("document approval", "inventory reservation"),
    ("device telemetry", "document approval"),
])
def test_root_fixture_does_not_leak_another_domain(tmp_path: Path, domain: str, foreign: str):
    payload = {
        "P1": {"doc_id": domain.replace(" ", "-"), "run_id": "r", "project_id": "p", "node_id": "n", "created_at": "fixed"},
        "P2": {"target_users": "operator", "pain_points": domain, "opportunity": domain},
        "P3": {"functional": [{"id": "REQ-001", "text": f"The system records {domain}.", "priority": "Must Have", "release_scope": "current", "requirement_kind": "atomic", "source_kind": "explicit", "evidence_refs": ["e:1"]}], "non_functional": []},
        "P4": {"contracts": [{"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "actor": "operator", "preconditions": ["authorized"], "trigger": "submit", "response": ["recorded"], "observable_oracles": ["record exists"], "boundaries": [{"condition": "empty", "response": "reject"}], "exceptions": [{"condition": "unavailable", "response": "report"}], "evidence_refs": ["e:1"]}]},
        "P5": {"metrics": []}, "P6": {},
    }
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    review_model = json.loads(json.dumps(payload))
    review_model["P1"]["parent_node_id"] = None
    review_model["P1"]["artifact_id"] = "prd:p:n:r"
    review_model["P1"]["artifact_type"] = "prd"
    review_model["P1"]["generator"] = "prd-generation"
    review_model["P1"]["requirement_ids"] = ["REQ-001"]
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"input_hash": _canonical_hash(review_model), "reviewer": "independent", "reviewed_at": "fixed", "status": "passed", "findings": []}), encoding="utf-8")
    output = tmp_path / "out"
    assert main(["--input", str(source), "--output-dir", str(output), "--review-artifact", str(review)]) == 0
    assert foreign not in (output / "prd.md").read_text(encoding="utf-8")
