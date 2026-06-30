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
- **追溯**：REQ-001。
""",
        encoding="utf-8",
    )
    (node_dir / "architecture" / "validation-report.md").write_text(
        """# Validation Report

## 4. 风险与缓解

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 对象存储上传失败 | REQ-001 | 允许重新上传并记录审计 |
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
