"""Tests for Markdown architecture package parsing in Derive mode."""
from __future__ import annotations

import zipfile
from pathlib import Path

from prd_flow.derive.context_builder import build_derive_context
from prd_flow.derive.parser import extract_module_context


def _write_architecture_package(path: Path) -> None:
    path.mkdir()
    (path / "README.md").write_text("# Architecture Package\n", encoding="utf-8")
    (path / "01-system-overview.md").write_text(
        """# 01 - System Overview

## Bounded Contexts

| Bounded Context | Responsibility |
| --- | --- |
| **Task Management Center** | Owns task lifecycle and plan generation. |
| **Execution Center** | Orchestrates command execution and recovery. |
| **Authorization Center** | Owns grants and runtime access checks. |
| **PC Agent Edge** | Runs commands on the user's local PC. |
""",
        encoding="utf-8",
    )
    (path / "02-module-partitioning.md").write_text(
        """# 02 - Module Partitioning

## Module Overview

| Module | Included BC | Responsibility | Reason |
| --- | --- | --- | --- |
| **Cloud Core** | Task Management Center, Execution Center, Authorization Center | Cloud control plane. | Shared transaction boundary. |
| **PC Agent Edge** | PC Agent Edge | Local runtime. | Physical PC boundary. |
""",
        encoding="utf-8",
    )
    (path / "03-runtime-architecture.md").write_text(
        """# 03 - Runtime Architecture

Execution Center sends commands to PC Agent Edge and receives StepExecuted or StepFailed events.
""",
        encoding="utf-8",
    )
    (path / "05-data-model.md").write_text(
        """# 05 - Data Model

### Execution Center

| Aggregate | Responsibility |
| --- | --- |
| ExecutionSession | Runtime command and result state. |
""",
        encoding="utf-8",
    )
    (path / "06-interface-contracts.md").write_text(
        """# 06 - Interface Contracts

### 6.1.4 Execute Command

- Provider: Execution Center
- Consumer: PC Agent Edge
- Protocol: gRPC over HTTPS
- Errors: `AGENT_OFFLINE`, `COMMAND_TIMEOUT`

### 6.1.5 Check Grants

- Provider: Authorization Center
- Consumer: Execution Center
- Protocol: internal API
- Errors: `GRANT_EXPIRED`
""",
        encoding="utf-8",
    )


def test_extract_bounded_context_from_architecture_directory(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)

    result = extract_module_context(arch_dir, "Execution Center", target_granularity="bounded_context")

    assert result["found"] is True
    assert result["target_granularity"] == "bounded_context"
    assert result["module"]["name"] == "Execution Center"
    assert "Cloud Core" in result["available_modules"]
    assert "Execution Center" in result["available_modules"]
    assert {iface["name"] for iface in result["module"]["interfaces"]} == {
        "Execute Command",
        "Check Grants",
    }
    assert any(dep["name"] == "PC Agent Edge" for dep in result["module"]["dependencies"])


def test_extract_deployable_module_from_readme_path(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)

    result = extract_module_context(arch_dir / "README.md", "Cloud Core")

    assert result["found"] is True
    assert result["target_granularity"] == "deployable_module"
    assert result["module"]["name"] == "Cloud Core"
    assert result["module"]["included_contexts"] == [
        "Task Management Center",
        "Execution Center",
        "Authorization Center",
    ]


def test_extract_from_zipped_architecture_package(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)
    zip_path = tmp_path / "architecture.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file in arch_dir.iterdir():
            archive.write(file, arcname=f"architecture/{file.name}")

    result = extract_module_context(zip_path, "PC Agent Edge", target_granularity="deployable_module")

    assert result["found"] is True
    assert result["module"]["name"] == "PC Agent Edge"
    assert "06-interface-contracts.md" in result["source_files"]


def test_build_context_uses_architecture_package_for_requirement_matching(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)
    parent_prd = tmp_path / "parent_prd.md"
    parent_prd.write_text(
        """---
doc_id: "ROOT-PRD-v1.0"
---

# Requirements

- [REQ-001] Execution Center shall execute commands through PC Agent Edge.
- [REQ-002] Authorization Center shall reject expired grants.
""",
        encoding="utf-8",
    )

    context = build_derive_context(parent_prd, arch_dir, "Execution Center", target_granularity="bounded_context")

    assert context["success"] is True
    assert context["parent_doc_id"] == "ROOT-PRD-v1.0"
    assert context["module_name"] == "Execution Center"
    assert [req["id"] for req in context["related_requirements"]] == ["REQ-001", "REQ-002"]
