"""Tests for run_derive_mode in prd_flow/main.py."""
from __future__ import annotations

import argparse
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
    target_module: str = "payment_gateway",
    output: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        parent_prd=parent_prd,
        parent_architecture=parent_architecture,
        target_module=target_module,
        output=output,
        resume=None,
    )


def _make_success_context(
    module_name: str = "payment_gateway",
    related_requirements: list[dict] | None = None,
    interfaces: list[dict] | None = None,
    dependencies: list[dict] | None = None,
    orphan_requirements: list[dict] | None = None,
) -> dict:
    return {
        "success": True,
        "parent_doc_id": "PARENT-PRD-v1.0",
        "parent_arch_id": "PARENT-ARCH-v1.0",
        "module_name": module_name,
        "module": {"name": module_name, "interfaces": interfaces or [], "dependencies": dependencies or []},
        "related_requirements": related_requirements or [],
        "interfaces": interfaces or [],
        "dependencies": dependencies or [],
        "orphan_requirements": orphan_requirements or [],
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
    assert state.draft_content["P1"]["doc_id"] == "PARENT-PRD-v1.0-PAYMENT-GATEWAY-v1.0"
    assert state.draft_content["P2"]["target_users"] == "系统用户"
    assert state.draft_content["P3"]["functional"][0]["id"] == "REQ-001-1"
    assert state.draft_content["P4"]["scenarios"][0]["scenario"] == "process_payment 正常调用"
    assert state.draft_content["P5"]["metrics"][0]["name"] == "接口响应时间"


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


@patch("prd_flow.main.assemble_prd")
@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_run_derive_mode_orphan_requirements_auto_included(
    mock_build_context: MagicMock,
    mock_save_session: MagicMock,
    mock_assemble_prd: MagicMock,
    tmp_path: Path,
) -> None:
    """Orphan requirements are automatically included with tentative=True."""
    context = _make_success_context(
        module_name="payment_gateway",
        related_requirements=[{"id": "REQ-001", "text": "支持支付"}],
        interfaces=[{"name": "pay", "method": "POST"}],
        dependencies=[],
        orphan_requirements=[{"id": "REQ-010", "text": "支付退款"}],
    )
    mock_build_context.return_value = context

    mock_assemble_prd.return_value = "# Derive PRD\n"

    output_file = tmp_path / "derive_output.md"
    args = _make_args(output=str(output_file))

    result = run_derive_mode(args)

    assert result == EXIT_SUCCESS
    assert output_file.exists()
    mock_save_session.assert_called_once()
    state = mock_save_session.call_args[0][0]

    # Orphan requirements should be merged into functional requirements
    functional = state.draft_content["P3"]["functional"]
    req_ids = [r["id"] for r in functional]
    assert "REQ-001-1" in req_ids
    assert "REQ-001-2" in req_ids
    assert "REQ-010-1" in req_ids
    assert "REQ-010-2" in req_ids

    # Check that orphan-derived reqs have tentative=True
    orphan_derived = [r for r in functional if r.get("parent_req") == "REQ-010"]
    assert len(orphan_derived) == 2
    for req in orphan_derived:
        assert req.get("tentative") is True


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
