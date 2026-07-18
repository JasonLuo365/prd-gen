import json
from pathlib import Path

from prd_flow.main import _canonical_hash, main


def _input_payload() -> dict:
    return {
        "P1": {"doc_id": "demo", "run_id": "r1", "project_id": "p1", "node_id": "root",
               "artifact_id": "prd:p1:root:r1", "artifact_type": "prd", "generator": "prd-generation",
               "created_at": "2026-07-18T00:00:00Z"},
        "P2": {"target_users": "operators", "pain_points": "manual work", "opportunity": "automation"},
        "P3": {"functional": [{"id": "REQ-001", "text": "The system records a submitted request.",
                                  "priority": "Must Have", "release_scope": "current", "requirement_kind": "atomic",
                                  "evidence_refs": ["decision:1"]}], "non_functional": []},
        "P4": {"contracts": [{"id": "AC-001", "type": "functional", "verifies": ["REQ-001"],
                                  "actor": "operator", "preconditions": ["authorized"], "trigger": "submit",
                                  "response": ["request is recorded"], "observable_oracles": ["record exists"],
                                  "boundaries": [{"condition": "empty request", "response": "reject"}],
                                  "exceptions": [{"condition": "storage unavailable", "response": "report failure"}],
                                  "evidence_refs": ["decision:1"]}]},
        "P5": {"metrics": []}, "P6": {},
    }


def test_noninteractive_root_writes_blocked_draft_and_sidecars(tmp_path: Path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_input_payload()), encoding="utf-8")
    output = tmp_path / "out"
    assert main(["--input", str(source), "--output-dir", str(output)]) == 2
    assert (output / "prd.draft.md").exists()
    for name in ("prd.json", "prd_manifest.json", "validation_report.json", "execution_log.json", "blocking_questions.json"):
        assert (output / name).exists()


def test_noninteractive_root_accepts_only_hash_bound_independent_review(tmp_path: Path):
    payload = _input_payload()
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    # This mirrors the canonical in-memory model after identity normalization.
    review_model = _input_payload()
    review_model["P1"]["parent_node_id"] = None
    review_model["P1"]["requirement_ids"] = ["REQ-001"]
    review = {"input_hash": _canonical_hash(review_model), "reviewer": "independent-reviewer",
              "reviewed_at": "2026-07-18T00:01:00Z", "status": "passed", "findings": []}
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    output = tmp_path / "out"
    assert main(["--input", str(source), "--output-dir", str(output), "--review-artifact", str(review_path)]) == 0
    assert (output / "prd.md").exists()
    manifest = json.loads((output / "prd_manifest.json").read_text(encoding="utf-8"))
    assert manifest["handoff_status"] == "PASS"
    report = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
    assert report["quality_statistics"]["functional_requirement_count"] == 1
    log = json.loads((output / "execution_log.json").read_text(encoding="utf-8"))
    for field in ("input_hash", "output_hash", "random_seed", "retry_count", "error_message"):
        assert field in log


def test_noninteractive_root_is_semantically_reproducible(tmp_path: Path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_input_payload()), encoding="utf-8")
    review_model = _input_payload()
    review_model["P1"]["parent_node_id"] = None
    review_model["P1"]["requirement_ids"] = ["REQ-001"]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"input_hash": _canonical_hash(review_model), "reviewer": "reviewer",
                                       "reviewed_at": "2026-07-18T00:01:00Z", "status": "passed", "findings": []}), encoding="utf-8")
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        assert main(["--input", str(source), "--output-dir", str(output), "--review-artifact", str(review_path), "--seed", "17"]) == 0
    assert (first / "prd.json").read_text(encoding="utf-8") == (second / "prd.json").read_text(encoding="utf-8")


def test_downstream_contract_accepts_ready_and_rejects_draft(tmp_path: Path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_input_payload()), encoding="utf-8")
    review_model = _input_payload()
    review_model["P1"]["parent_node_id"] = None
    review_model["P1"]["requirement_ids"] = ["REQ-001"]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"input_hash": _canonical_hash(review_model), "reviewer": "reviewer",
                                       "reviewed_at": "2026-07-18T00:01:00Z", "status": "passed", "findings": []}), encoding="utf-8")
    ready, draft = tmp_path / "ready", tmp_path / "draft"
    assert main(["--input", str(source), "--output-dir", str(ready), "--review-artifact", str(review_path)]) == 0
    assert main(["--input", str(source), "--output-dir", str(draft)]) == 2
    ready_manifest = json.loads((ready / "prd_manifest.json").read_text(encoding="utf-8"))
    draft_manifest = json.loads((draft / "prd_manifest.json").read_text(encoding="utf-8"))
    ready_prd = json.loads((ready / "prd.json").read_text(encoding="utf-8"))
    assert ready_manifest["handoff_status"] == "PASS"
    assert ready_manifest["artifact_id"] == ready_prd["P1"]["artifact_id"]
    assert draft_manifest["handoff_status"] == "FAIL"
