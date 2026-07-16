"""Tests for Leaf Gate artifact discovery and evidence preparation."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_leaf_gate_module():
    script = Path("leaf-gate-skill/leaf-gate/scripts/run_leaf_gate.py")
    spec = importlib.util.spec_from_file_location("run_leaf_gate", script)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["run_leaf_gate"] = module
    spec.loader.exec_module(module)
    return module


def _write_node(node_dir: Path) -> None:
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        """# Requirements

## Must Have

- [REQ-001] 系统应支持上传 1 到 3 张 JPG/PNG 图片。

## Could Have

- [REQ-002] 系统可记录提示轮次用于后续学习分析。

## Non-goals

- 本节点不覆盖错题本。
""",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """# 部分冻结产物：REQ-002 因缺少确定 oracle 未进入本 Feature。
Feature: 图片上传

  @REQ-001 @TC-001
  Scenario: 接受 1 到 3 张 JPG 或 PNG 图片
    Given 学生已登录
    When 学生上传 1 到 3 张 JPG 或 PNG 图片
    Then 系统接受图片并进入校验流程

  @MET-001 @TC-MET-001
  Scenario: 图片上传校验响应 P95
    Given 已完成 1000 次图片上传
    When 统计上传校验响应时间
    Then P95 小于等于 2 秒
""",
        encoding="utf-8",
    )
    output_dir = node_dir / "architecture" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "01-system-overview.md").write_text(
        """# 01 - System Overview

| BC | Responsibility |
| --- | --- |
| Problem Intake BC | 图片上传、格式校验、数量校验 |
""",
        encoding="utf-8",
    )
    (output_dir / "05-data-model.md").write_text(
        """# 05 - Data Model

ProblemImage 状态包含 uploaded、validating、valid、invalid。
""",
        encoding="utf-8",
    )
    (output_dir / "06-interface-contracts.md").write_text(
        """# 06 - Interface Contracts

### 图片上传

- **输入**：1-3 个 JPG/PNG 图片文件。
- **输出**：imageUploadId、uploadedAt、status。
- **错误码**：400 表示图片数量或格式非法。
- **状态**：uploaded -> validating -> valid / invalid。
- **副作用**：写入图片元数据并发送 ImageUploaded 事件。
- **依赖**：Object Storage。
""",
        encoding="utf-8",
    )
    (node_dir / "architecture" / "validation-report.md").write_text(
        """# Validation Report

## 4. 风险与缓解

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 对象存储上传失败 | 图片上传 | 允许重新上传并记录审计 |
""",
        encoding="utf-8",
    )


def _write_mixed_feedback_node(node_dir: Path) -> None:
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        """# Requirements

- [REQ-D001] Problem Intake Module supports JPG/PNG image upload.
- [REQ-D002] Problem Intake Module rejects more than 3 images.
""",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """Feature: Problem Intake

  @REQ-D001 @TC-D001
  Scenario: Upload JPG or PNG image
    Given the student is signed in
    When the student uploads a JPG image
    Then the system accepts the image
""",
        encoding="utf-8",
    )
    output_dir = node_dir / "architecture" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "06-interface-contracts.md").write_text(
        """# Interface Contracts

### Upload Image

- **inputs**: 1 to 3 JPG/PNG images.
- **outputs**: imageId, status.
- **errors**: 400 for invalid image format.
- **state**: uploaded -> validated.
- **dependencies**: Object Storage.
""",
        encoding="utf-8",
    )


def test_find_artifacts_uses_architecture_output_package(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    _write_node(node_dir)

    artifacts = leaf_gate.find_artifacts(node_dir)

    assert artifacts.architecture == node_dir / "architecture" / "output"
    assert node_dir / "architecture" / "output" / "06-interface-contracts.md" in artifacts.architecture_files
    assert node_dir / "architecture" / "validation-report.md" in artifacts.architecture_validation_files
    assert node_dir / "architecture" / "validation-report.md" not in artifacts.architecture_files


def test_architecture_roles_are_discovered_from_manifest_and_semantics(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    node_dir.mkdir()
    architecture = node_dir / "architecture"
    delivery = architecture / "release-bundle"
    validation = architecture / "验证结果"
    delivery.mkdir(parents=True)
    validation.mkdir()

    (architecture / "architecture-workbench.md").write_text("# Architecture Workbench\n\nDraft only.\n", encoding="utf-8")
    (architecture / "architecture-generation-plan.md").write_text("# Architecture generation plan\n", encoding="utf-8")
    (delivery / "index.md").write_text(
        "# Architecture package index\n\n"
        "- [Overview](foundation.md)\n"
        "- [Runtime](execution.md)\n"
        "- [Contracts](public-boundaries.md)\n",
        encoding="utf-8",
    )
    (delivery / "foundation.md").write_text("# 系统概览\n\n系统上下文与模块职责。\n", encoding="utf-8")
    (delivery / "execution.md").write_text("# 运行时架构\n\n失败处理与状态流转。\n", encoding="utf-8")
    contract = delivery / "public-boundaries.md"
    contract.write_text(
        "# 接口契约\n\n输入、输出、错误、状态、副作用、依赖。\n",
        encoding="utf-8",
    )
    report = validation / "架构验证报告.md"
    report.write_text("# 架构验证报告\n\n## 风险与缓解\n", encoding="utf-8")
    plan = validation / "architecture-modification-plan.md"
    plan.write_text("# Architecture modification plan\n", encoding="utf-8")

    artifacts = leaf_gate.find_artifacts(node_dir)

    assert artifacts.architecture == delivery
    assert artifacts.architecture_selection == "manifest-links"
    assert artifacts.architecture_manifest == delivery / "index.md"
    assert contract in artifacts.architecture_files
    assert report in artifacts.architecture_validation_files
    assert plan in artifacts.architecture_remediation_files
    assert architecture / "architecture-workbench.md" in artifacts.architecture_supporting_files
    assert report not in artifacts.architecture_files
    assert plan not in artifacts.architecture_files


def test_recursive_yaml_manifest_and_compact_derived_allocations_are_authoritative(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-recursive"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        "REQ-D001: Resolve the query.\nREQ-D002: Preserve unmapped constraints.\nNFR-D001: Finish within 3 seconds.\n",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """Feature: recursive child
  @REQ-D001
  Scenario: resolve query
    Given a query
    When it is resolved
    Then a semantic query is returned

  @REQ-D002
  Scenario: preserve constraints
    Given an unmapped constraint
    When the query is resolved
    Then the constraint remains visible

  @NFR-D001
  Scenario: meet deadline
    Given a query
    When it is resolved
    Then it finishes within 3 seconds
""",
        encoding="utf-8",
    )
    architecture = node_dir / "architecture"
    architecture.mkdir()
    manifest = architecture / "architecture-manifest.yaml"
    manifest.write_text(
        "generated_artifacts:\n  - 02-architecture-decomposition.md\n  - 04-contracts-and-runtime.md\n",
        encoding="utf-8",
    )
    decomposition = architecture / "02-architecture-decomposition.md"
    decomposition.write_text(
        """# 子节点注册表
| child_id | 责任 | 分配需求 |
|---|---|---|
| query-resolution | 查询解析与约束保留。 | D001-D002、NFR-D001 |
""",
        encoding="utf-8",
    )
    (architecture / "04-contracts-and-runtime.md").write_text(
        "# 契约\n\n输入、输出、错误、状态、副作用、依赖。\n",
        encoding="utf-8",
    )

    artifacts = leaf_gate.find_artifacts(node_dir)
    traceability = leaf_gate.build_traceability_text(artifacts)

    assert artifacts.architecture_manifest == manifest
    assert artifacts.architecture_selection == "manifest-links"
    assert decomposition in artifacts.architecture_files
    assert traceability.count("| strong | covered |") == 3
    assert "explicit requirement allocation" in traceability


def test_validation_report_cannot_substitute_for_final_architecture_evidence(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-node"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text("REQ-777: System frobnicates a request.\n", encoding="utf-8")
    (node_dir / "testcase.feature").write_text(
        "Feature: request\n\n  @REQ-777\n  Scenario: frobnicate\n"
        "    Given a request\n    When it is submitted\n    Then resultId is returned\n",
        encoding="utf-8",
    )
    output = node_dir / "architecture" / "output"
    output.mkdir(parents=True)
    (output / "contracts.md").write_text(
        "# Interface Contracts\n\ninputs, outputs, errors, states, side effects, dependencies.\n",
        encoding="utf-8",
    )
    (node_dir / "architecture" / "validation-report.md").write_text(
        "# Validation Report\n\nREQ-777 is covered by FrobnicatingService and resultId.\n",
        encoding="utf-8",
    )

    artifacts = leaf_gate.find_artifacts(node_dir)
    traceability = leaf_gate.build_traceability_text(artifacts)

    assert "| REQ-777 |" in traceability
    assert "| covered |" not in traceability


def test_flat_validated_architecture_package_needs_no_validation_report(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-flat"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text("REQ-001: System accepts an upload request.\n", encoding="utf-8")
    (node_dir / "testcase.feature").write_text(
        "Feature: upload\n\n  @REQ-001\n  Scenario: upload\n"
        "    Given a valid file\n    When it is uploaded\n    Then uploadId is returned\n",
        encoding="utf-8",
    )
    architecture = node_dir / "architecture"
    architecture.mkdir()
    (architecture / "README.md").write_text(
        "# Effective architecture package\n\n- [Public boundary](public-boundary.md)\n",
        encoding="utf-8",
    )
    (architecture / "public-boundary.md").write_text(
        "# Interface contract\n\nREQ-001\n\n"
        "- inputs: file\n- outputs: uploadId\n- errors: invalid file\n"
        "- states: accepted\n- side effects: stores metadata\n- dependencies: object store\n",
        encoding="utf-8",
    )

    report = leaf_gate.build_report(node_dir, None)
    artifacts = report["static_checks"]["artifacts"]

    assert artifacts["architecture"] == str(architecture)
    assert artifacts["architecture_selection"] == "manifest-links"
    assert artifacts["architecture_validation_files"] == []
    assert report["phase"] == "STATIC_EVIDENCE"
    assert report["decision"] is None


def test_find_artifacts_ignores_leaf_gate_refinement_markdown(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-identity"
    _write_node(node_dir)
    (node_dir / "leaf-gate.refinement.architecture.md").write_text(
        """# Leaf Gate Refinement Suggestions: architecture

This generated handoff is not an architecture source artifact.
""",
        encoding="utf-8",
    )

    artifacts = leaf_gate.find_artifacts(node_dir)

    assert artifacts.architecture == node_dir / "architecture" / "output"
    assert node_dir / "leaf-gate.refinement.architecture.md" not in artifacts.architecture_files
    assert node_dir / "architecture" / "output" / "06-interface-contracts.md" in artifacts.architecture_files


def test_contract_fields_accept_snake_case_side_effects() -> None:
    leaf_gate = _load_leaf_gate_module()
    architecture_text = """# Interface Contracts

| field | value |
|---|---|
| inputs | request body |
| outputs | response body |
| errors | 400 invalid |
| states | created -> active |
| side_effects | creates auth session and writes audit record |
| dependencies | Redis, Audit Log |
"""

    fields = leaf_gate.contract_fields(architecture_text)

    assert fields == {
        "inputs": True,
        "outputs": True,
        "errors": True,
        "states": True,
        "side_effects": True,
        "dependencies": True,
    }


def test_architecture_obligation_ids_are_current_leaf_requirements() -> None:
    leaf_gate = _load_leaf_gate_module()
    requirements = leaf_gate.parse_requirements(
        """# Requirements

- [REQ-A001] Deliver the student-facing frontend and browser-level verification.
  parent_req: REQ-001
- [REQ-DB001] Apply the initial database migration from an empty database.
  parent_req: REQ-002
- [REQ-EVT001] Publish ProblemSubmitted after persistence succeeds.
  parent_req: REQ-003
"""
    )

    assert [requirement.id for requirement in requirements] == [
        "REQ-A001",
        "REQ-DB001",
        "REQ-EVT001",
    ]
    assert [requirement.parent_id for requirement in requirements] == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
    ]


def test_build_report_prepares_traceability_and_risks(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    _write_node(node_dir)

    report = leaf_gate.build_report(node_dir, None)

    traceability = node_dir / "traceability.md"
    risks = node_dir / "risks.md"
    assert traceability.exists()
    assert risks.exists()
    assert "REQ-001" in traceability.read_text(encoding="utf-8")
    assert "REQ-002" in traceability.read_text(encoding="utf-8")
    assert "deferred" in traceability.read_text(encoding="utf-8")
    assert "对象存储上传失败" in risks.read_text(encoding="utf-8")
    assert "architecture" not in report["static_checks"]["artifacts"]["missing"]
    assert "traceability" not in report["static_checks"]["artifacts"]["missing"]
    assert "risks" not in report["static_checks"]["artifacts"]["missing"]


def test_deferred_requirements_and_metric_scenarios_do_not_fail_traceability(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    _write_node(node_dir)

    report = leaf_gate.build_report(node_dir, None)
    c4_evidence = report["static_checks"]["C4_verifiability"]["evidence"]

    assert "REQ-002" not in c4_evidence["unmapped_requirements"]
    assert "图片上传校验响应 P95" not in c4_evidence["untagged_scenarios"]


def test_architecture_evidence_strength_covers_without_req_id(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    _write_node(node_dir)

    report = leaf_gate.build_report(node_dir, None)
    traceability_text = (node_dir / "traceability.md").read_text(encoding="utf-8")
    c4_evidence = report["static_checks"]["C4_verifiability"]["evidence"]

    assert "| REQ-001 |" in traceability_text
    assert "06-interface-contracts.md" in traceability_text
    assert "| strong | covered |" in traceability_text
    assert c4_evidence["architecture_evidence_gaps"] == []


def test_derive_requirements_use_current_ids_and_preserve_parent_trace(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-tutoring-session"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        """# Requirements

## Must Have

- [REQ-D001] Tutoring Session Module 应在自身职责边界内满足父需求：系统应要求学生在开始答疑前选择基础水平，基础水平枚举为：薄弱 / 中等 / 较好。
  - parent_req: REQ-004

## Non-functional Requirements

- [NFR-D001] Tutoring Session Module 应在模块边界内继承父级非功能约束：答疑结果必须在会话内可追溯到对应题目图片和基础水平选择。
  - parent_req: NFR-004
""",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """Feature: Tutoring Session

  @REQ-D001 @TC-D001
  Scenario: Student starts tutoring after selecting foundation level
    Given 学生已选择基础水平为薄弱
    When 学生开始答疑
    Then 系统创建 TutoringSession 并记录基础水平

  @NFR-D001 @TC-NFR-D001
  Scenario: Tutoring result is traceable to problem image and foundation level
    Given 已存在包含图片 ID 和基础水平的 TutoringSession
    When 查询答疑结果
    Then 结果关联到对应题目图片和基础水平选择
""",
        encoding="utf-8",
    )
    output_dir = node_dir / "architecture" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "06-interface-contracts.md").write_text(
        """# 06 - Interface Contracts

### Start Tutoring Session

- **输入**：imageId、proficiencyLevel（薄弱 / 中等 / 较好）。
- **输出**：sessionId、status、selectedProficiencyLevel。
- **错误码**：400 表示未选择基础水平。
- **状态**：created -> active。
- **副作用**：写入 TutoringSession，并记录图片 ID 与基础水平关联。
- **依赖**：Problem Intake 提供已校验图片引用。
""",
        encoding="utf-8",
    )

    report = leaf_gate.build_report(node_dir, None)
    traceability_text = (node_dir / "traceability.md").read_text(encoding="utf-8")
    c4_evidence = report["static_checks"]["C4_verifiability"]["evidence"]

    assert report["static_checks"]["requirements"]["ids"] == ["NFR-D001", "REQ-D001"]
    assert "REQ-004" not in report["static_checks"]["requirements"]["ids"]
    assert "NFR-004" not in report["static_checks"]["requirements"]["ids"]
    assert "parent_req: REQ-004" in traceability_text
    assert "| REQ-D001 |" in traceability_text
    assert "| NFR-D001 |" in traceability_text
    assert c4_evidence["unmapped_requirements"] == []
    assert c4_evidence["architecture_evidence_gaps"] == []


def test_weak_architecture_evidence_is_an_upstream_input_error(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        """# Requirements

- [REQ-001] 系统应支持学生上传 3 张 JPG/PNG 图片。
""",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """Feature: 图片上传

  @REQ-001 @TC-001
  Scenario: 上传图片
    Given 学生已登录
    When 学生上传 3 张 JPG 图片
    Then 系统接受图片
""",
        encoding="utf-8",
    )
    output_dir = node_dir / "architecture" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "01-system-overview.md").write_text(
        """# 01 - System Overview

系统支持 JPG/PNG。
""",
        encoding="utf-8",
    )

    try:
        leaf_gate.build_report(node_dir, None)
    except leaf_gate.LeafGateInputError as exc:
        error = exc
    else:
        raise AssertionError("Expected an upstream validation input error")
    traceability_text = (node_dir / "traceability.md").read_text(encoding="utf-8")

    assert "| weak | weak_evidence |" in traceability_text
    assert error.code == "UPSTREAM_VALIDATION_INCOMPLETE"
    assert error.details["architecture_evidence_gaps"] == ["REQ-001: weak_evidence"]
    assert "decision" not in error.to_report()


def test_contract_and_testcase_gaps_are_not_layering_decisions(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-mixed-feedback"
    node_dir.mkdir()
    (node_dir / "prd.md").write_text(
        """# Requirements

- [REQ-D001] Problem Intake Module 应支持学生上传 JPG/PNG 图片。
- [REQ-D002] Problem Intake Module 应拒绝超过 3 张图片。
""",
        encoding="utf-8",
    )
    (node_dir / "testcase.feature").write_text(
        """Feature: Problem Intake

  @REQ-D001 @TC-D001
  Scenario: Upload JPG or PNG image
    Given 学生已登录
    When 学生上传 JPG 图片
    Then 系统接受图片
""",
        encoding="utf-8",
    )
    output_dir = node_dir / "architecture" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "06-interface-contracts.md").write_text(
        """# Interface Contracts

### Upload Image

- **输入**：1 到 3 张 JPG/PNG 图片。
- **输出**：imageId、status。
- **错误码**：400 表示格式非法。
- **状态**：uploaded -> validated。
- **依赖**：Object Storage。
""",
        encoding="utf-8",
    )

    try:
        leaf_gate.build_report(node_dir, None)
    except leaf_gate.LeafGateInputError as exc:
        error = exc
    else:
        raise AssertionError("Expected an upstream validation input error")

    assert error.code == "UPSTREAM_VALIDATION_INCOMPLETE"
    assert error.details["missing_contract_fields"] == ["side_effects"]
    assert error.details["unmapped_requirements"] == ["REQ-D002"]


def test_valid_semantic_judgement_stops_layering(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-problem-intake"
    _write_node(node_dir)
    llm_path = node_dir / "leaf-gate.llm.json"
    judgement = {
        criterion: {
            "status": "pass",
            "confidence": 0.9,
            "evidence": [f"Artifact evidence for {criterion}."],
            "reason": "Further layering has no material benefit.",
        }
        for criterion in leaf_gate.CRITERIA
    }
    llm_path.write_text(
        json.dumps(
            {
                "node_id": "L1-problem-intake",
                "llm_judgement": judgement,
                "recommended_decision": "STOP_LAYERING",
                "summary": "No useful child boundary remains.",
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    report = leaf_gate.build_report(node_dir, llm_path)
    assert report["decision"] == "STOP_LAYERING"
    assert report["phase"] == "FINAL"
    assert report["next_action"]["type"] == "vibecode"
    assert "refinement_routes" not in report


def test_main_writes_input_error_without_refinement_outputs(tmp_path: Path, monkeypatch) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-mixed-feedback"
    _write_mixed_feedback_node(node_dir)
    output = node_dir / "leaf-gate.report.json"

    monkeypatch.setattr(sys, "argv", ["run_leaf_gate.py", str(node_dir), "--output", str(output)])

    assert leaf_gate.main() == 2
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "INPUT_ERROR"
    assert payload["error"] == "UPSTREAM_VALIDATION_INCOMPLETE"
    assert "decision" not in payload
    assert not (node_dir / "leaf-gate.refinement.md").exists()
    assert not (node_dir / "leaf-gate.refinement.architecture.md").exists()
    assert not (node_dir / "leaf-gate.refinement.testcase.md").exists()
