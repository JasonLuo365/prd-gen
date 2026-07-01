"""Tests for Leaf Gate artifact discovery and evidence preparation."""
from __future__ import annotations

import importlib.util
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


def test_find_artifacts_uses_architecture_output_package(tmp_path: Path) -> None:
    leaf_gate = _load_leaf_gate_module()
    node_dir = tmp_path / "L0-root"
    _write_node(node_dir)

    artifacts = leaf_gate.find_artifacts(node_dir)

    assert artifacts.architecture == node_dir / "architecture" / "output"
    assert node_dir / "architecture" / "output" / "06-interface-contracts.md" in artifacts.architecture_files
    assert node_dir / "architecture" / "validation-report.md" in artifacts.architecture_files


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


def test_weak_architecture_evidence_fails_without_human_review(tmp_path: Path) -> None:
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

系统包含图片相关能力。
""",
        encoding="utf-8",
    )

    report = leaf_gate.build_report(node_dir, None)
    traceability_text = (node_dir / "traceability.md").read_text(encoding="utf-8")
    c4 = report["static_checks"]["C4_verifiability"]

    assert "| weak | weak_evidence |" in traceability_text
    assert c4["status"] == "fail"
    assert c4["evidence"]["architecture_evidence_gaps"] == ["REQ-001: weak_evidence"]
    assert report["decision"] == "NEEDS_SPEC_REFINEMENT"
