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
    assert node_dir / "architecture" / "validation-report.md" in artifacts.architecture_files


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


def test_weak_architecture_evidence_routes_to_architecture_refinement(tmp_path: Path) -> None:
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

    report = leaf_gate.build_report(node_dir, None)
    traceability_text = (node_dir / "traceability.md").read_text(encoding="utf-8")
    c4 = report["static_checks"]["C4_verifiability"]

    assert "| weak | weak_evidence |" in traceability_text
    assert c4["status"] == "fail"
    assert c4["evidence"]["architecture_evidence_gaps"] == ["REQ-001: weak_evidence"]
    assert report["decision"] == "NEEDS_REFINEMENT"
    routes = report["refinement_routes"]
    assert any(route["target"] == "architecture" for route in routes)


def test_refinement_routes_split_architecture_and_testcase_feedback(tmp_path: Path) -> None:
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

    report = leaf_gate.build_report(node_dir, None)
    routes = report["refinement_routes"]

    assert report["decision"] == "NEEDS_REFINEMENT"
    architecture_routes = [route for route in routes if route["target"] == "architecture"]
    testcase_routes = [route for route in routes if route["target"] == "testcase"]
    assert architecture_routes
    assert testcase_routes
    assert any("side_effects" in action for route in architecture_routes for action in route["actions"])
    assert any("REQ-D002" in action for route in testcase_routes for action in route["actions"])


def test_target_refinement_markdown_only_contains_target_routes(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-mixed-feedback"
    _write_mixed_feedback_node(node_dir)

    report = leaf_gate.build_report(node_dir, None)
    architecture_markdown = leaf_gate.render_refinement_markdown(report, target="architecture")
    testcase_markdown = leaf_gate.render_refinement_markdown(report, target="testcase")

    assert "# Leaf Gate Refinement Suggestions: architecture" in architecture_markdown
    assert "architecture/output/06-interface-contracts.md" in architecture_markdown
    assert "side_effects" in architecture_markdown
    assert "testcase.feature" not in architecture_markdown
    assert "REQ-D002" not in architecture_markdown

    assert "# Leaf Gate Refinement Suggestions: testcase" in testcase_markdown
    assert "testcase.feature" in testcase_markdown
    assert "REQ-D002" in testcase_markdown
    assert "architecture/output/06-interface-contracts.md" not in testcase_markdown
    assert "side_effects" not in testcase_markdown


def test_llm_refinement_routes_preserve_target_specific_feedback(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-problem-intake"
    _write_node(node_dir)
    llm_path = node_dir / "leaf-gate.llm.json"
    llm_path.write_text(
        json.dumps(
            {
                "node_id": "L1-problem-intake",
                "llm_judgement": {
                    "C1_behavior_complexity": {
                        "status": "pass",
                        "confidence": 0.9,
                        "evidence": ["testcase.feature covers a single upload behavior group."],
                        "reason": "Behavior scope is narrow enough.",
                    },
                    "C2_contract_boundary": {
                        "status": "pass",
                        "confidence": 0.9,
                        "evidence": ["architecture/output/06-interface-contracts.md defines API fields."],
                        "reason": "Contract boundary is explicit.",
                    },
                    "C3_ai_context_control": {
                        "status": "pass",
                        "confidence": 0.9,
                        "evidence": ["No AI-owned context is present in this node."],
                        "reason": "AI context is not a blocker.",
                    },
                    "C4_verifiability": {
                        "status": "warn",
                        "confidence": 0.86,
                        "evidence": ["testcase.feature lacks a precise 200ms acceptance probe."],
                        "reason": "Testcase owner must add the missing performance probe.",
                    },
                    "C5_risk_decomposition": {
                        "status": "pass",
                        "confidence": 0.9,
                        "evidence": ["risks.md has no unresolved high risk."],
                        "reason": "No decomposition-caused risk remains.",
                    },
                },
                "recommended_decision": "NEEDS_REFINEMENT",
                "summary": "Needs testcase refinement only.",
                "refinement_routes": [
                    {
                        "target": "testcase",
                        "criterion": "C4_verifiability",
                        "reason": "The performance oracle belongs in testcase evidence.",
                        "actions": ["Add a tagged scenario that measures the 200ms upload acknowledgement."],
                        "evidence": ["testcase.feature lacks a precise 200ms acceptance probe."],
                    }
                ],
                "suggested_next_action": {"type": "refine_spec", "children": [], "notes": []},
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    report = leaf_gate.build_report(node_dir, llm_path)
    routes = report["refinement_routes"]

    assert report["decision"] == "NEEDS_REFINEMENT"
    assert any(route["target"] == "testcase" for route in routes)
    assert not any(
        route["target"] == "owner_decision" and route["criterion"] == "C4_verifiability"
        for route in routes
    )
    testcase_markdown = leaf_gate.render_refinement_markdown(report, target="testcase")
    assert "200ms upload acknowledgement" in testcase_markdown


def test_main_writes_split_refinement_markdown_next_to_json_output(tmp_path: Path, monkeypatch) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L1-mixed-feedback"
    _write_mixed_feedback_node(node_dir)
    output = node_dir / "leaf-gate.report.json"

    monkeypatch.setattr(sys, "argv", ["run_leaf_gate.py", str(node_dir), "--output", str(output)])

    assert leaf_gate.main() == 0
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["decision"] == "NEEDS_REFINEMENT"
    index = node_dir / "leaf-gate.refinement.md"
    architecture = node_dir / "leaf-gate.refinement.architecture.md"
    testcase = node_dir / "leaf-gate.refinement.testcase.md"
    assert index.exists()
    assert architecture.exists()
    assert testcase.exists()

    index_text = index.read_text(encoding="utf-8")
    assert "leaf-gate.refinement.architecture.md" in index_text
    assert "leaf-gate.refinement.testcase.md" in index_text
    assert "side_effects" not in index_text
    assert "REQ-D002" not in index_text

    architecture_text = architecture.read_text(encoding="utf-8")
    assert "architecture/output/06-interface-contracts.md" in architecture_text
    assert "side_effects" in architecture_text
    assert "testcase.feature" not in architecture_text
    assert "REQ-D002" not in architecture_text

    testcase_text = testcase.read_text(encoding="utf-8")
    assert "testcase.feature" in testcase_text
    assert "REQ-D002" in testcase_text
    assert "architecture/output/06-interface-contracts.md" not in testcase_text
    assert "side_effects" not in testcase_text
