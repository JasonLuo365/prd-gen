"""Black-box tests for the portable skill launcher and frozen handoff shape."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "prd-generation" / "scripts" / "run_prd_flow.py"
CONTRACT = ROOT / "skills" / "prd-generation" / "references" / "downstream-prd-contract.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *arguments],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )


def _write_ready_parent(path: Path) -> None:
    path.write_text(
        """---
doc_id: ROOT-RESERVATION
status: approved
ready_for_test_generation: true
---
# Requirements
### Must Have
- [REQ-001] The system records a reservation request.
  - release_scope: current
  - requirement_kind: atomic
  - evidence_refs: [decision:reservation]

# Acceptance Contracts
## AC-001 reservation record
- type: functional
- verifies: [REQ-001]
- actor: operator
- preconditions: [a valid request exists]
- trigger: submit the request
- response: [the request record is available]
- observable_oracles: [a record can be retrieved]
- boundaries: [empty request -> reject]
- exceptions: [storage unavailable -> report failure]
- evidence_refs: [decision:reservation]
""",
        encoding="utf-8",
    )


def test_portable_launcher_runs_real_derive_and_emits_contract_sidecars(tmp_path: Path) -> None:
    parent = tmp_path / "parent.md"
    _write_ready_parent(parent)
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-module-partitioning.md").write_text(
        """# Module allocation

| Module | Responsibility | Source Requirement |
| --- | --- | --- |
| **Reservation Processor** | Records and retrieves reservation requests. | REQ-001 |
""",
        encoding="utf-8",
    )
    output = tmp_path / "child.md"

    completed = _run(
        "--parent-prd", str(parent),
        "--architecture-package", str(architecture),
        "--target-module", "Reservation Processor",
        "--output", str(output),
        "--run-id", "cli-run", "--project-id", "reservation", "--node-id", "reservation-processor",
        "--seed", "17", "--created-at", "2026-07-18T00:00:00+00:00",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert output.exists()
    sidecars = {name: json.loads((tmp_path / name).read_text(encoding="utf-8")) for name in (
        "prd.json", "prd_manifest.json", "validation_report.json", "execution_log.json",
    )}
    assert sidecars["prd.json"]["functional_requirements"][0]["id"] == "REQ-D001"
    assert sidecars["prd.json"]["functional_requirements"][0]["parent_req"] == "REQ-001"
    assert sidecars["prd.json"]["requirement_id_mapping"]["REQ-001"] == "REQ-D001"
    assert sidecars["prd_manifest.json"]["status"] == "PASS"
    assert sidecars["execution_log.json"]["code_version"]
    assert sidecars["execution_log.json"]["schema_version"] == "2.0"

    frozen = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for field in frozen["required_manifest_fields"]:
        assert field in sidecars["prd_manifest.json"]
    assert sidecars["prd_manifest.json"]["status"] == frozen["ready_requirements"]["status"]
    assert sidecars["prd.json"]["status"] in frozen["ready_requirements"]["prd_status"]
    rendered = output.read_text(encoding="utf-8")
    assert not any(marker in rendered for marker in frozen["forbidden_fields"])


def test_portable_launcher_help_is_clean() -> None:
    completed = _run("--help")
    assert completed.returncode == 0
    assert "--architecture-package" in completed.stdout


def test_portable_launcher_rejects_missing_upstream_without_writing_output(tmp_path: Path) -> None:
    output = tmp_path / "child.md"
    completed = _run(
        "--parent-prd", str(tmp_path / "missing.md"),
        "--architecture-package", str(tmp_path / "missing-architecture"),
        "--target-module", "Any Module", "--output", str(output),
    )
    assert completed.returncode == 1
    assert "INPUT_FILE_ERROR" in completed.stdout
    assert not output.exists()


def test_portable_launcher_returns_schema_exit_code_for_incompatible_input(tmp_path: Path) -> None:
    source = tmp_path / "incompatible.json"
    source.write_text(json.dumps({"schema_version": "1.0", "P1": {}, "P3": {}}), encoding="utf-8")
    completed = _run("--input", str(source), "--output-dir", str(tmp_path / "out"))
    assert completed.returncode == 5
    assert "SCHEMA_INCOMPATIBLE" in completed.stdout

    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_text(json.dumps({"P1": {}, "P3": {"functional": "not-a-list"}}), encoding="utf-8")
    completed = _run("--input", str(wrong_shape), "--output-dir", str(tmp_path / "wrong-shape-out"))
    assert completed.returncode == 5
    assert "INPUT_SCHEMA_ERROR" in completed.stdout
