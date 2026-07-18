import json
import sys
from pathlib import Path

import pytest

from scripts import run_leaf_gate


def _common(node_id: str = "node-01") -> dict:
    return {
        "schema_version": "1.0", "run_id": "run-01", "project_id": "project-01", "node_id": node_id,
        "parent_node_id": "root", "artifact_id": "input-artifact", "artifact_type": "input", "created_at": "2026-01-01T00:00:00Z",
        "generator": "fixture", "status": "PASS", "input_artifacts": [], "requirement_ids": ["REQ-001", "REQ-002"],
    }


def _write_case(tmp_path: Path, *, architecture: dict | None = None, mocktest: dict | None = None, depth: int = 0) -> None:
    common = _common()
    (tmp_path / "prd.json").write_text(json.dumps(common | {"artifact_id": "prd:node-01", "artifact_type": "prd", "depth": depth, "max_depth": 4, "node_history": [], "requirements": ["REQ-001", "REQ-002"]}), encoding="utf-8")
    (tmp_path / "architecture.json").write_text(json.dumps(common | {"artifact_id": "architecture:node-01", "artifact_type": "architecture"} | (architecture or {"components": ["upload"], "interfaces": ["upload-api"], "dependencies": ["store"], "depth": 1, "complexity": 3, "risks": []})), encoding="utf-8")
    (tmp_path / "testcases.json").write_text(json.dumps(common | {"artifact_id": "testcases:node-01", "artifact_type": "testcases", "requirement_ids": ["REQ-001", "REQ-002"], "testcases": [{"id": "TC-001", "requirement_ids": ["REQ-001"], "status": "PASS"}, {"id": "TC-002", "requirement_ids": ["REQ-002"], "status": "PASS"}]}), encoding="utf-8")
    (tmp_path / "mocktest_report.json").write_text(json.dumps(common | {"artifact_id": "mocktest:node-01", "artifact_type": "mocktest_report"} | (mocktest or {"status": "PASS", "defects": []})), encoding="utf-8")


def test_structured_stop_output_and_downstream_contract(tmp_path: Path) -> None:
    _write_case(tmp_path)
    report = run_leaf_gate.build_structured_report(tmp_path)

    assert report["decision"] == report["status"] == "STOP_LAYERING"
    assert report["proposed_children"] == []
    assert {"schema_version", "run_id", "project_id", "node_id", "parent_node_id", "artifact_id", "artifact_type", "created_at", "generator", "status", "input_artifacts", "requirement_ids", "decision", "confidence", "rationale", "evidence_refs", "triggered_rules", "complexity_metrics", "risk_metrics", "mocktest_summary", "proposed_children", "warnings"} <= report.keys()
    assert [item["code"] for item in report["rationale"]] == ["SINGLE_RESPONSIBILITY", "INTERFACES_CLEAR", "REQUIREMENTS_VERIFIABLE", "ARCHITECTURE_RISK_ACCEPTABLE", "MOCKTEST_READY"]


def test_structured_continue_generates_scheduler_ready_children(tmp_path: Path) -> None:
    _write_case(tmp_path, architecture={"components": ["ingest", "verify"], "interfaces": ["upload-api"], "dependencies": [], "depth": 1, "complexity": 3, "risks": []})
    (tmp_path / "leaf-gate.config.json").write_text(json.dumps({"thresholds": {"max_components": 1}}), encoding="utf-8")

    report = run_leaf_gate.build_structured_report(tmp_path)

    assert report["decision"] == "CONTINUE_LAYERING"
    assert report["triggered_rules"] == ["components-exceed-threshold"]
    assert len(report["proposed_children"]) == 2
    assert {"child_node_id", "name", "responsibility", "requirement_ids", "decomposition_rationale", "expected_interfaces", "priority"} <= report["proposed_children"][0].keys()
    assert report["proposed_children"][0]["expected_interfaces"] == ["upload-api"]


@pytest.mark.parametrize("status", ["FAIL", "ERROR"])
def test_mocktest_failure_never_stops_layering(tmp_path: Path, status: str) -> None:
    _write_case(tmp_path, mocktest={"status": status, "defects": []})
    with pytest.raises(run_leaf_gate.LeafGateInputError) as caught:
        run_leaf_gate.build_structured_report(tmp_path)
    report = run_leaf_gate.formal_error_report(caught.value, tmp_path)
    assert report["decision"] == report["status"] == "ERROR"
    assert report["rationale"][0]["code"] == "MOCKTEST_NOT_PASS"


def test_missing_evidence_and_identity_mismatch_are_errors(tmp_path: Path) -> None:
    _write_case(tmp_path)
    (tmp_path / "mocktest_report.json").unlink()
    with pytest.raises(run_leaf_gate.LeafGateInputError) as missing:
        run_leaf_gate.build_structured_report(tmp_path)
    assert missing.value.code == "MISSING_REQUIRED_EVIDENCE"

    _write_case(tmp_path)
    mock = json.loads((tmp_path / "mocktest_report.json").read_text(encoding="utf-8"))
    mock["node_id"] = "other-node"
    (tmp_path / "mocktest_report.json").write_text(json.dumps(mock), encoding="utf-8")
    with pytest.raises(run_leaf_gate.LeafGateInputError) as mismatch:
        run_leaf_gate.build_structured_report(tmp_path)
    assert mismatch.value.code == "ARTIFACT_IDENTITY_MISMATCH"


def test_missing_common_field_or_node_history_is_a_schema_error(tmp_path: Path) -> None:
    _write_case(tmp_path)
    architecture = json.loads((tmp_path / "architecture.json").read_text(encoding="utf-8"))
    del architecture["generator"]
    (tmp_path / "architecture.json").write_text(json.dumps(architecture), encoding="utf-8")
    with pytest.raises(run_leaf_gate.LeafGateInputError) as missing_common:
        run_leaf_gate.build_structured_report(tmp_path)
    assert missing_common.value.code == "ARTIFACT_IDENTITY_MISMATCH"

    _write_case(tmp_path)
    prd = json.loads((tmp_path / "prd.json").read_text(encoding="utf-8"))
    del prd["node_history"]
    (tmp_path / "prd.json").write_text(json.dumps(prd), encoding="utf-8")
    with pytest.raises(run_leaf_gate.LeafGateInputError) as history_error:
        run_leaf_gate.build_structured_report(tmp_path)
    assert history_error.value.code == "SCHEMA_INCOMPATIBLE"


def test_legacy_status_is_mapped_without_becoming_formal_output(tmp_path: Path) -> None:
    _write_case(tmp_path)
    architecture = json.loads((tmp_path / "architecture.json").read_text(encoding="utf-8"))
    architecture["status"] = "LEAF_READY"
    (tmp_path / "architecture.json").write_text(json.dumps(architecture), encoding="utf-8")
    report = run_leaf_gate.build_structured_report(tmp_path)
    assert report["status"] == report["decision"] == "STOP_LAYERING"
    assert "legacy_status_mapped:architecture.json:LEAF_READY->STOP_LAYERING" in report["warnings"]


def test_depth_limit_reports_error_when_node_remains_complex(tmp_path: Path) -> None:
    _write_case(tmp_path, architecture={"components": ["one", "two"], "interfaces": [], "dependencies": [], "depth": 1, "complexity": 3, "risks": []}, depth=2)
    (tmp_path / "leaf-gate.config.json").write_text(json.dumps({"thresholds": {"max_components": 1, "max_recursion_depth": 2}}), encoding="utf-8")
    report = run_leaf_gate.build_structured_report(tmp_path)
    assert report["decision"] == "ERROR"
    assert "depth_limit_reached" in report["warnings"]


def test_threshold_boundary_and_repeated_decision_are_deterministic(tmp_path: Path) -> None:
    _write_case(tmp_path, architecture={"components": ["one", "two"], "interfaces": [], "dependencies": [], "depth": 1, "complexity": 2, "risks": []})
    (tmp_path / "leaf-gate.config.json").write_text(json.dumps({"thresholds": {"max_components": 2, "max_complexity": 2}}), encoding="utf-8")
    first = run_leaf_gate.build_structured_report(tmp_path)
    second = run_leaf_gate.build_structured_report(tmp_path)
    for key in ("decision", "triggered_rules", "proposed_children", "confidence", "complexity_metrics", "risk_metrics"):
        assert first[key] == second[key]
    assert first["decision"] == "STOP_LAYERING"


def test_formal_artifacts_include_metrics_log_and_annotation_template(tmp_path: Path) -> None:
    _write_case(tmp_path)
    report = run_leaf_gate.build_structured_report(tmp_path)
    output = tmp_path / "out"
    run_leaf_gate.write_formal_artifacts(report, output, "2026-01-01T00:00:00Z")
    assert {"leaf_gate_decision.json", "leaf_gate_decision.md", "leaf_gate_metrics.json", "execution_log.json", "leaf_gate_annotation_template.json"} == {path.name for path in output.iterdir()}
    annotation = json.loads((output / "leaf_gate_annotation_template.json").read_text(encoding="utf-8"))
    assert annotation["node_id"] == "node-01"
    assert annotation["label_options"] == ["CONTINUE_LAYERING", "STOP_LAYERING", "CANNOT_JUDGE"]
    assert annotation["input_summary"]["complexity_metrics"]["requirement_count"] == 2
    common_fields = {"schema_version", "run_id", "project_id", "node_id", "parent_node_id", "artifact_id", "artifact_type", "created_at", "generator", "status", "input_artifacts", "requirement_ids"}
    for filename in ("leaf_gate_decision.json", "leaf_gate_metrics.json", "execution_log.json"):
        payload = json.loads((output / filename).read_text(encoding="utf-8"))
        assert common_fields <= payload.keys(), filename


def test_formal_schema_and_downstream_contract_match_generated_output(tmp_path: Path) -> None:
    _write_case(tmp_path)
    report = run_leaf_gate.build_structured_report(tmp_path)
    schema_path = Path(__file__).parent.parent / "schemas" / "leaf_gate_decision.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert set(schema["required"]).issubset(report)
    run_leaf_gate.validate_formal_report(report)
    assert report["artifact_type"] == "leaf_gate_decision"
    assert report["status"] == "STOP_LAYERING"


def test_cli_detects_structured_mode_and_writes_formal_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_case(tmp_path)
    output = tmp_path / "result" / "custom.json"
    monkeypatch.setattr(sys, "argv", ["run_leaf_gate.py", str(tmp_path), "--output", str(output)])
    assert run_leaf_gate.main() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["decision"] == "STOP_LAYERING"
    assert (output.parent / "execution_log.json").exists()


def test_all_documented_boundary_fixtures_are_runnable(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "structured_cases.json"
    bundle = json.loads(fixture_path.read_text(encoding="utf-8"))
    for name, case in bundle["cases"].items():
        case_dir = tmp_path / name
        case_dir.mkdir()
        for filename, artifact in bundle["artifacts"].items():
            if filename in case.get("remove", []):
                continue
            payload = bundle["common"] | artifact | case.get("overrides", {}).get(filename, {})
            (case_dir / filename).write_text(json.dumps(payload), encoding="utf-8")
        try:
            report = run_leaf_gate.build_structured_report(case_dir)
        except run_leaf_gate.LeafGateInputError as error:
            report = run_leaf_gate.formal_error_report(error, case_dir)
        assert report["decision"] == case["expected_decision"], name
