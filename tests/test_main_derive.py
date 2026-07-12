"""Tests for run_derive_mode in prd_flow/main.py."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prd_flow.main import (
    run_derive_mode,
    EXIT_SUCCESS,
    EXIT_INPUT_ERROR,
    EXIT_QUALITY_BLOCKED,
)
from prd_flow.quality.smart_req import SMARTResult


def _make_args(
    parent_prd: str = "parent.md",
    parent_architecture: str = "arch.yaml",
    architecture_package: str | None = None,
    target_module: str = "payment_gateway",
    target_granularity: str = "auto",
    output: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        parent_prd=parent_prd,
        parent_architecture=parent_architecture,
        architecture_package=architecture_package,
        target_module=target_module,
        target_granularity=target_granularity,
        output=output,
        resume=None,
    )


def _make_success_context(
    module_name: str = "payment_gateway",
    related_requirements: list[dict] | None = None,
    interfaces: list[dict] | None = None,
    dependencies: list[dict] | None = None,
    events: list[dict] | None = None,
    external_dependencies: list[dict] | None = None,
    orphan_requirements: list[dict] | None = None,
    related_non_functional: list[dict] | None = None,
    related_success_metrics: list[dict] | None = None,
    related_scenarios: list[dict] | None = None,
    data_assets: list[dict] | None = None,
    requirement_surfaces: dict[str, list[str]] | None = None,
    implementation_surfaces: list[str] | None = None,
    coverage_gaps: list[str] | None = None,
    non_goals: list[str] | None = None,
) -> dict:
    return {
        "success": True,
        "parent_doc_id": "PARENT-PRD-v1.0",
        "parent_arch_id": "PARENT-ARCH-v1.0",
        "module_name": module_name,
        "module": {"name": module_name, "interfaces": interfaces or [], "dependencies": dependencies or []},
        "related_requirements": related_requirements or [],
        "related_non_functional": related_non_functional or [],
        "related_success_metrics": related_success_metrics or [],
        "related_scenarios": related_scenarios or [],
        "interfaces": interfaces or [],
        "dependencies": dependencies or [],
        "events": events or [],
        "external_dependencies": external_dependencies or [],
        "data_assets": data_assets or [],
        "requirement_surfaces": requirement_surfaces or {},
        "implementation_surfaces": implementation_surfaces or [],
        "orphan_requirements": orphan_requirements or [],
        "coverage_gaps": coverage_gaps or [],
        "non_goals": non_goals or [],
        "error": None,
        "available_modules": ["payment_gateway", "user_service"],
    }


@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_success(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    tmp_path: Path,
) -> None:
    """Full derive mode workflow — fully automated, no input mocked."""
    mock_build_context.return_value = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[
            {"id": "REQ-001", "text": "用户可以通过支付网关完成交易"},
        ],
        interfaces=[
            {"name": "process_payment", "method": "POST"},
            {"name": "refund", "method": "POST"},
        ],
        dependencies=[
            {"name": "bank_api"},
        ],
    )

    mock_assemble_prd.return_value = "# Derive PRD\n"

    output_file = tmp_path / "derive_output.md"
    args = _make_args(output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "# Derive PRD\n"

    mock_save_session.assert_called_once()
    state = mock_save_session.call_args[0][0]
    assert state.mode == "derive"
    assert state.target_module == "payment_gateway"
    mock_build_context.assert_called_once()
    assert mock_build_context.call_args.args[1] == Path("arch.yaml")
    assert mock_build_context.call_args.kwargs["target_granularity"] == "auto"
    assert state.draft_content["P1"]["doc_id"] == "PARENT-PRD-v1.0-PAYMENT-GATEWAY-v1.0"
    assert state.draft_content["P2"]["target_users"] == "该模块的上游调用方和受其行为影响的系统用户"
    assert state.draft_content["P3"]["functional"][0]["id"] == "REQ-D001"
    assert state.draft_content["P4"]["scenarios"][0]["scenario"] == "REQ-D001 覆盖父需求 REQ-001"
    assert state.draft_content["P5"]["metrics"][0]["name"] == "Must Have 范围预算"


@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_accepts_architecture_package(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    tmp_path: Path,
) -> None:
    """New architecture package input is preferred over legacy parent_architecture."""
    mock_build_context.return_value = _make_success_context(
        module_name="Execution Center",
        related_requirements=[{"id": "REQ-001", "text": "Execution Center executes commands"}],
        interfaces=[{"name": "Execute Command", "method": "gRPC"}],
        dependencies=[],
    )
    mock_assemble_prd.return_value = "# Derive PRD\n"

    output_file = tmp_path / "derive_output.md"
    args = _make_args(
        parent_architecture=None,
        architecture_package="architecture",
        target_module="Execution Center",
        target_granularity="bounded_context",
        output=str(output_file),
    )

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    assert output_file.exists()
    mock_build_context.assert_called_once()
    assert mock_build_context.call_args.args[1] == Path("architecture")
    assert mock_build_context.call_args.kwargs["target_granularity"] == "bounded_context"
    mock_save_session.assert_called_once()


@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_does_not_invent_latency_or_incomplete_interface_scenarios(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    tmp_path: Path,
) -> None:
    mock_build_context.return_value = _make_success_context(
        module_name="Identity Module",
        related_requirements=[
            {"id": "REQ-001", "text": "系统应支持学生通过手机号登录", "priority": "Must Have"},
        ],
        interfaces=[
            {"name": "LLM Service", "method": "POST", "request_fields": [], "response_fields": [], "error_codes": []},
        ],
        dependencies=[],
    )
    mock_assemble_prd.return_value = "# Derive PRD\n"

    output_file = tmp_path / "derive_output.md"
    args = _make_args(target_module="Identity Module", output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    state = mock_save_session.call_args[0][0]
    functional_text = "\n".join(req["text"] for req in state.draft_content["P3"]["functional"])
    scenario_text = "\n".join(
        " ".join(str(value) for value in scenario.values())
        for scenario in state.draft_content["P4"]["scenarios"]
    )
    assert "200ms" not in functional_text
    assert "LLM Service" not in scenario_text
    assert "返回状态 200" not in scenario_text
    assert "返回状态 400" not in scenario_text


@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_module_not_found(
    mock_build_context: MagicMock,
) -> None:
    """When target module is not found and no similar match, returns EXIT_INPUT_ERROR."""
    mock_build_context.return_value = {
        "success": False,
        "parent_doc_id": "PARENT-PRD-v1.0",
        "parent_arch_id": "UNKNOWN",
        "module_name": "unknown_module",
        "module": None,
        "related_requirements": [],
        "interfaces": [],
        "dependencies": [],
        "error": "模块 'unknown_module' 不存在于架构设计中",
        "available_modules": ["payment_gateway", "user_service"],
    }

    args = _make_args(target_module="unknown_module")

    result = run_derive_mode(args)
    assert result == EXIT_INPUT_ERROR


@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_auto_fixes_similar_module(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    tmp_path: Path,
) -> None:
    """When target module not found but a similar name exists (edit distance <= 2), auto-correct."""
    not_found_context = {
        "success": False,
        "parent_doc_id": "PARENT-PRD-v1.0",
        "parent_arch_id": "UNKNOWN",
        "module_name": "payment_gatway",
        "module": None,
        "related_requirements": [],
        "interfaces": [],
        "dependencies": [],
        "error": "模块 'payment_gatway' 不存在于架构设计中",
        "available_modules": ["payment_gateway", "user_service"],
    }
    success_context = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[{"id": "REQ-001", "text": "支持支付"}],
        interfaces=[{"name": "pay", "method": "POST"}],
        dependencies=[],
    )
    mock_build_context.side_effect = [not_found_context, success_context]

    mock_assemble_prd.return_value = "# Derive PRD\n"

    output_file = tmp_path / "derive_output.md"
    args = _make_args(target_module="payment_gatway", output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "# Derive PRD\n"
    mock_save_session.assert_called_once()
    state = mock_save_session.call_args[0][0]
    assert state.target_module == "payment_gateway"


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_reports_orphans_without_blocking_current_target(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    """An unassigned sibling requirement stays visible without blocking this target."""
    context = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[{"id": "REQ-001", "text": "支持支付"}],
        interfaces=[{"name": "pay", "method": "POST"}],
        dependencies=[],
        orphan_requirements=[{"id": "REQ-010", "text": "支付退款"}],
    )
    mock_build_context.return_value = context

    output_file = tmp_path / "derive_output.md"
    args = _make_args(output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    assert output_file.exists()
    coverage = json.loads(output_file.with_suffix(".coverage.json").read_text(encoding="utf-8"))
    assert coverage["status"] == "allocation_incomplete"
    assert coverage["items"] == [
        {
            "id": "REQ-001",
            "kind": "requirement",
            "owners": ["payment_gateway"],
            "status": "inherited_by_target",
        },
        {
            "id": "REQ-010",
            "kind": "requirement",
            "owners": [],
            "status": "unassigned",
        },
    ]
    mock_save_session.assert_called_once()


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_generates_one_child_requirement_per_parent_requirement(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    """Derive narrows scope instead of splitting every parent requirement into interface/core pairs."""
    mock_build_context.return_value = _make_success_context(
        module_name="Identity Module",
        related_requirements=[
            {"id": "REQ-015", "text": "系统应支持学生通过手机号和短信验证码登录。", "priority": "Must Have"},
            {"id": "REQ-016", "text": "系统应生成 6 位数字短信验证码。", "priority": "Must Have"},
        ],
        interfaces=[{"name": "短信验证码发送", "method": "POST"}],
        dependencies=[],
    )

    output_file = tmp_path / "derive_output.md"
    args = _make_args(target_module="Identity Module", output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    mock_save_session.assert_called_once()
    state = mock_save_session.call_args[0][0]
    functional = state.draft_content["P3"]["functional"]
    parent_functional = [req for req in functional if req.get("source_kind") == "parent_requirement"]
    assert [req["parent_req"] for req in parent_functional] == ["REQ-015", "REQ-016"]
    assert all(not req["id"].endswith("-1") and not req["id"].endswith("-2") for req in functional)
    assert "REQ-015" in output_file.read_text(encoding="utf-8")


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_preserves_could_have_with_original_priority(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    """Could Have remains visible as deferred scope instead of being silently deleted."""
    mock_build_context.return_value = _make_success_context(
        module_name="Tutoring Session Module",
        related_requirements=[
            {"id": "REQ-004", "text": "系统应要求学生在开始答疑前选择基础水平。", "priority": "Must Have"},
            {"id": "REQ-012", "text": "系统可记录学生本题的提示轮次和是否查看完整解答。", "priority": "Could Have"},
        ],
        interfaces=[],
        dependencies=[],
    )

    output_file = tmp_path / "derive_output.md"
    args = _make_args(target_module="Tutoring Session Module", output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    mock_save_session.assert_called_once()
    state = mock_save_session.call_args[0][0]
    functional = state.draft_content["P3"]["functional"]
    parent_functional = [req for req in functional if req.get("source_kind") == "parent_requirement"]
    assert [req["parent_req"] for req in parent_functional] == ["REQ-004", "REQ-012"]
    assert parent_functional[1]["priority"] == "Could Have"
    output_text = output_file.read_text(encoding="utf-8")
    assert "REQ-012" in output_text
    assert "可记录" in output_text


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_preserves_frontend_scenario_and_adds_data_migration(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    mock_build_context.return_value = _make_success_context(
        module_name="Image Submission Component",
        related_requirements=[
            {
                "id": "REQ-D002",
                "text": "前端应禁止添加第 4 张图片；后端应拒绝超过 3 张图片的请求。",
                "priority": "Must Have",
            }
        ],
        related_non_functional=[
            {"id": "NFR-D001", "text": "图片上传校验响应 P95 <= 2 秒"},
            {"id": "NFR-D002", "text": "上传数据必须可追溯"},
            {"id": "NFR-D003", "text": "原始图片保存时间不得超过 30 天"},
        ],
        related_scenarios=[
            {
                "feature": "图片上传与输入校验",
                "scenario": "已选择 3 张图片后不能添加第 4 张",
                "requirement_ids": ["REQ-D002"],
                "steps": [
                    {"keyword": "Given", "text": "学生已选择 3 张图片"},
                    {"keyword": "When", "text": "学生尝试继续添加第 4 张图片"},
                    {"keyword": "Then", "text": "前端不允许继续添加图片"},
                ],
            }
        ],
        data_assets=[
            {"name": "ImageSubmission", "source": "05-data-model.md"},
        ],
        requirement_surfaces={"REQ-D002": ["frontend", "api_backend", "domain_logic"]},
        implementation_surfaces=["frontend", "api_backend", "domain_logic", "database_migration"],
        non_goals=["当前版本不支持视频题目输入。"],
    )

    output_file = tmp_path / "derive_output.md"
    result = run_derive_mode(
        _make_args(target_module="Image Submission Component", output=str(output_file))
    )

    assert result == EXIT_SUCCESS
    state = mock_save_session.call_args[0][0]
    functional = state.draft_content["P3"]["functional"]
    assert functional[0]["implementation_surfaces"] == ["frontend", "api_backend", "domain_logic"]
    frontend_requirement = next(
        req for req in functional if req.get("source_kind") == "architecture_frontend"
    )
    data_requirement = next(
        req for req in functional if req.get("source_kind") == "architecture_data"
    )
    assert frontend_requirement["related_reqs"] == ["REQ-D001"]
    assert frontend_requirement["implementation_surfaces"] == ["frontend"]
    assert data_requirement["implementation_surfaces"] == ["database_migration"]
    assert len(state.draft_content["P3"]["non_functional"]) == 3
    inherited = state.draft_content["P4"]["scenarios"][0]
    assert inherited["steps"][-1] == {"keyword": "Then", "text": "前端不允许继续添加图片"}
    output_text = output_file.read_text(encoding="utf-8")
    assert "@REQ-D001" in output_text
    assert "Then 前端不允许继续添加图片" in output_text
    assert "source_kind: architecture_frontend" in output_text
    assert "related_reqs: [REQ-D001]" in output_text
    assert "implementation_surfaces: [database_migration]" in output_text
    assert "parent_nfr: NFR-D003" in output_text
    assert "当前版本不支持视频题目输入。" in output_text


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_generates_unique_architecture_artifact_requirements(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    mock_build_context.return_value = _make_success_context(
        module_name="Compliance Module",
        related_requirements=[
            {"id": "REQ-001", "text": "系统应记录并处理删除结果。", "priority": "Must Have"}
        ],
        interfaces=[
            {
                "name": "Readability Check",
                "contract_id": "INT-RC-001",
                "method": "CALL",
                "path": "",
                "request_fields": ["resource_id"],
                "response_fields": ["readability_status"],
                "error_codes": [],
            }
        ],
        data_assets=[{"name": "RetentionPolicy", "source": "05-data-model.md"}],
        events=[
            {
                "contract_id": "EVT-RC-001",
                "event_name": "DataDeleted",
                "publisher": "Compliance Module",
                "consumers": "Audit",
                "required_fields": ["event_id", "resource_id"],
                "produced_fields": ["resource_id"],
                "side_effects": "Records deletion evidence.",
            }
        ],
        external_dependencies=[
            {"name": "Object Storage", "source": "03-runtime-architecture.md", "evidence": "deletion ACL"}
        ],
        related_success_metrics=[
            {
                "id": "MET-DELETE",
                "name": "MET-DELETE 删除成功率",
                "target": "= 100%",
                "method": "统计删除任务结果。",
            }
        ],
        implementation_surfaces=[
            "api_backend",
            "domain_logic",
            "database_migration",
            "worker_job",
            "external_adapter",
            "observability",
            "integration_wiring",
        ],
    )

    result = run_derive_mode(_make_args(output=str(tmp_path / "derived.md")))

    assert result == EXIT_SUCCESS
    functional = mock_save_session.call_args[0][0].draft_content["P3"]["functional"]
    ids = [req["id"] for req in functional]
    assert len(ids) == len(set(ids))
    assert {req.get("source_kind") for req in functional} >= {
        "architecture_interface",
        "architecture_data",
        "architecture_event",
        "architecture_adapter",
        "architecture_worker",
        "architecture_observability",
        "architecture_runtime",
    }
    assert any(
        metric["name"] == "MET-DELETE 删除成功率"
        for metric in mock_save_session.call_args[0][0].draft_content["P5"]["metrics"]
    )


@patch("prd_flow.main.save_session")
def test_recursive_derive_keeps_frontend_api_and_migration_end_to_end(
    _mock_save_session: MagicMock,
    tmp_path: Path,
) -> None:
    root_prd = tmp_path / "root.md"
    root_prd.write_text(
        """---
doc_id: VERTICAL-SLICE-v1.0
---
# Requirements
### Must Have
- [REQ-002] 系统应限制最多 3 张图片；前端禁止第 4 张；后端拒绝超过 3 张的请求。
# Acceptance
```gherkin
Feature: 图片数量限制
  @REQ-002
  Scenario: 第四张图片被阻止
    Given 学生已选择 3 张图片
    When 学生添加第 4 张图片
    Then 前端不允许继续添加图片
    And 后端返回图片数量超限错误
```
""",
        encoding="utf-8",
    )
    root_arch = tmp_path / "root-architecture"
    root_arch.mkdir()
    (root_arch / "02-module-partitioning.md").write_text(
        """| Module | Included BC | Responsibility |
|---|---|---|
| **Problem Intake Module** | Problem Intake BC | 隐私提示、图片上传、数量限制、格式/大小校验 |
""",
        encoding="utf-8",
    )
    (root_arch / "05-data-model.md").write_text(
        """## 1. Problem Intake BC
### 聚合根
| 聚合根 | 说明 |
|---|---|
| `ProblemImage` | 图片元数据 |
""",
        encoding="utf-8",
    )
    (root_arch / "06-interface-contracts.md").write_text(
        """### Upload Images
- Provider: Problem Intake Module
- Path: `POST /api/v1/problems/images`
- **required_fields**: `images`
- **produced_fields**: `image_ids`, `status`
- **error_codes**: `TOO_MANY_IMAGES`
""",
        encoding="utf-8",
    )
    l1_prd = tmp_path / "l1.md"

    first_result = run_derive_mode(
        _make_args(
            parent_prd=str(root_prd),
            parent_architecture=None,
            architecture_package=str(root_arch),
            target_module="Problem Intake Module",
            target_granularity="deployable_module",
            output=str(l1_prd),
        )
    )
    assert first_result == EXIT_SUCCESS

    child_arch = tmp_path / "child-architecture"
    child_arch.mkdir()
    (child_arch / "02-module-partitioning.md").write_text(
        """| Component | Responsibility | Related Aggregate |
|---|---|---|
| Image Submission Component | 学生端前端页面、图片选择与提交、数量限制、对象存储写入 | ImageSubmission |
""",
        encoding="utf-8",
    )
    (child_arch / "05-data-model.md").write_text(
        """## Aggregate Roots
| Aggregate Root | Responsibility | Stored In |
|---|---|---|
| ImageSubmission | 图片集提交 | PostgreSQL |
""",
        encoding="utf-8",
    )
    (child_arch / "06-interface-contracts.md").write_text(
        """### Upload Images
- Provider: Image Submission Component
- Path: `POST /api/v1/problems/images`
- **required_fields**: `images`
- **produced_fields**: `image_ids`, `status`
- **error_codes**: `TOO_MANY_IMAGES`
""",
        encoding="utf-8",
    )
    l2_prd = tmp_path / "l2.md"

    second_result = run_derive_mode(
        _make_args(
            parent_prd=str(l1_prd),
            parent_architecture=None,
            architecture_package=str(child_arch),
            target_module="Image Submission Component",
            target_granularity="component",
            output=str(l2_prd),
        )
    )

    assert second_result == EXIT_SUCCESS
    output_text = l2_prd.read_text(encoding="utf-8")
    assert "Then 前端不允许继续添加图片" in output_text
    assert "And 后端返回图片数量超限错误" in output_text
    assert "implementation_surfaces: [frontend, api_backend, domain_logic]" in output_text
    assert "source_kind: architecture_frontend" in output_text
    assert "implementation_surfaces: [database_migration]" in output_text
    assert "POST /api/v1/problems/images" in output_text


@patch("prd_flow.main._write_error_report")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_blocks_when_must_budget_is_exceeded(
    mock_build_context: MagicMock,
    mock_write_error_report: MagicMock,
    tmp_path: Path,
) -> None:
    """Derive quality gate blocks outputs that are too broad for a focused child PRD."""
    mock_build_context.return_value = _make_success_context(
        module_name="large_module",
        related_requirements=[
            {"id": f"REQ-{idx:03d}", "text": f"模块必须支持第 {idx} 个可观察行为。", "priority": "Must Have"}
            for idx in range(1, 10)
        ],
        interfaces=[],
        dependencies=[],
    )

    output_file = tmp_path / "derive_output.md"
    args = _make_args(target_module="large_module", output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_QUALITY_BLOCKED
    mock_write_error_report.assert_called_once()


@patch("prd_flow.main._write_error_report")
@patch("prd_flow.main._run_smart_check")
@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_smart_fix_failure_returns_quality_blocked(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    mock_run_smart_check: MagicMock,
    mock_write_error_report: MagicMock,
    tmp_path: Path,
) -> None:
    """SMART check fails and auto-fix cannot resolve it — returns EXIT_QUALITY_BLOCKED."""
    mock_build_context.return_value = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[{"id": "REQ-001", "text": "支持支付"}],
        interfaces=[{"name": "pay", "method": "POST"}],
        dependencies=[],
    )

    mock_assemble_prd.return_value = "# Derive PRD\n"

    # First and second SMART check both fail (auto-fix doesn't help)
    failing_result = SMARTResult(
        req_id="REQ-001-1",
        specific=False,
        measurable=False,
        achievable=True,
        relevant=True,
        testable=False,
        issues=["包含模糊量词: 良好", "无可量化指标，建议补充具体数值"],
    )
    mock_run_smart_check.return_value = [failing_result]

    output_file = tmp_path / "derive_output.md"
    args = _make_args(output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_QUALITY_BLOCKED
    mock_write_error_report.assert_called_once()
    mock_save_session.assert_not_called()


@patch("prd_flow.main._write_error_report")
@patch("prd_flow.main.scan_ambiguity")
@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_ambiguity_logic_conflict_returns_quality_blocked(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    mock_scan_ambiguity: MagicMock,
    mock_write_error_report: MagicMock,
    tmp_path: Path,
) -> None:
    """Ambiguity scan finds logic conflicts — returns EXIT_QUALITY_BLOCKED."""
    mock_build_context.return_value = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[{"id": "REQ-001", "text": "支持支付"}],
        interfaces=[{"name": "pay", "method": "POST"}],
        dependencies=[],
    )

    mock_assemble_prd.return_value = "# Derive PRD\n"

    # Ambiguity scan returns logic conflicts
    mock_scan_ambiguity.return_value = {
        "lexical": [],
        "logic": [{"type": "conflict", "description": "需求之间存在逻辑矛盾"}],
        "completeness": [],
    }

    output_file = tmp_path / "derive_output.md"
    args = _make_args(output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_QUALITY_BLOCKED
    mock_write_error_report.assert_called_once()
    mock_save_session.assert_not_called()
