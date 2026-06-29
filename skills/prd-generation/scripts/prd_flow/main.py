"""Main CLI entry point for PRD Flow."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from prd_flow.mode_detector import Mode, detect_mode
from prd_flow.output.assembler import assemble_prd
from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.phases.problem_statement import ProblemStatementPhase
from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.quality.ambiguity import scan_ambiguity
from prd_flow.quality.reporter import format_quality_report
from prd_flow.quality.smart_req import check_smart_req
from prd_flow.quality.suggest import suggest_fix
from prd_flow.derive.context_builder import build_derive_context
from prd_flow.derive.decision_rules import find_best_module_match, resolve_orphan_requirements
from prd_flow.derive.auto_fixer import (
    fix_vague_quantifiers,
    fix_measurable,
    fix_parent_req,
    generate_interface_scenarios,
)
from prd_flow.session import SessionState, save_session, load_session

EXIT_SUCCESS = 0
EXIT_INPUT_ERROR = 1
EXIT_QUALITY_BLOCKED = 2


def _run_smart_check(state: SessionState) -> list:
    """对P3的功能需求运行SMART-REQ检查。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return [check_smart_req(req) for req in functional]


def _check_gherkin_coverage(state: SessionState) -> list[dict]:
    """检查每条 Must-Have 需求是否至少对应一个 Gherkin 场景。

    Returns: 缺少场景覆盖的 Must-Have 需求列表
    """
    functional = state.draft_content.get("P3", {}).get("functional", [])
    scenarios = state.draft_content.get("P4", {}).get("scenarios", [])
    must_have = [r for r in functional if r.get("priority") == "Must Have"]

    uncovered = []
    for req in must_have:
        req_id = req.get("id", "")
        # Check if any scenario references this requirement
        has_coverage = False
        for s in scenarios:
            scenario_text = f"{s.get('feature', '')} {s.get('scenario', '')}"
            if req_id in scenario_text:
                has_coverage = True
                break
        # Also check gherkin_count as fallback
        if not has_coverage and req.get("gherkin_count", 0) >= 1:
            has_coverage = True
        if not has_coverage:
            uncovered.append(req)

    return uncovered


def _run_ambiguity_check(state: SessionState, prd_text: str) -> dict:
    """对PRD文本运行歧义扫描。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return scan_ambiguity(prd_text, functional)


def _ask_continue(prompt: str) -> bool:
    """询问用户是否继续。"""
    answer = input(f"{prompt} (y/n): ").strip().lower()
    return answer in ("y", "yes", "是")


def _write_error_report(state: SessionState, errors: list, args: argparse.Namespace) -> None:
    """Write draft PRD and JSON error report on quality failure."""
    # Assemble partial PRD and write to .draft.md
    prd_text = assemble_prd(state.draft_content)
    parent_doc = state.draft_content.get("P1", {}).get("parent_doc", "unknown")
    module_name = state.draft_content.get("P1", {}).get("module_name", "unknown")
    version = state.draft_content.get("P1", {}).get("version", "1.0.0")
    draft_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name}_prd_v{version}.md")
    draft_path = draft_path.with_suffix(".draft.md")
    draft_path.write_text(prd_text, encoding="utf-8")

    # Write JSON error report to .draft.errors.json
    errors_path = draft_path.with_suffix(".draft.errors.json")
    errors_path.write_text(
        json.dumps({"errors": errors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n草稿PRD已保存至: {draft_path}")
    print(f"错误报告已保存至: {errors_path}")


def _resume_session(session_path: Path, args: argparse.Namespace) -> None:
    """从会话文件恢复并继续流程。"""
    state = load_session(session_path)
    print(f"恢复会话: {state.session_id}, 模式: {state.mode}")

    phase_order = [
        ("P1", FrontmatterPhase),
        ("P2", ProblemStatementPhase),
        ("P3", RequirementsPhase),
        ("P4", AcceptancePhase),
        ("P5", SuccessMetricsPhase),
    ]

    for phase_id, PhaseClass in phase_order:
        if phase_id in state.completed_phases:
            # Print brief summary
            data = state.draft_content.get(phase_id, {})
            if phase_id == "P1":
                print(f"[{phase_id}] 已完成 - 文档ID: {data.get('doc_id', 'N/A')}")
            elif phase_id == "P2":
                pain_points = data.get("pain_points", "")
                summary = pain_points[:30] + "..." if len(pain_points) > 30 else pain_points
                print(f"[{phase_id}] 已完成 - 目标用户: {data.get('target_users', 'N/A')}, 痛点: {summary}")
            elif phase_id == "P3":
                functional = data.get("functional", [])
                print(f"[{phase_id}] 已完成 - 功能需求: {len(functional)} 条")
            elif phase_id == "P4":
                scenarios = data.get("scenarios", [])
                print(f"[{phase_id}] 已完成 - 验收场景: {len(scenarios)} 个")
            elif phase_id == "P5":
                metrics = data.get("metrics", [])
                print(f"[{phase_id}] 已完成 - 成功指标: {len(metrics)} 个")

            if _ask_continue("是否要修改此阶段"):
                phase = PhaseClass(state)
                phase.run()
        else:
            print(f"[{phase_id}] 未完成，继续执行...")
            phase = PhaseClass(state)
            phase.run()

    # Final assembly
    prd_text = assemble_prd(state.draft_content)

    # Quality gate after P3 (if P3 was completed or just run)
    smart_results = _run_smart_check(state)
    report = format_quality_report(smart_results=smart_results)
    print(report)

    if not all(r.overall_pass for r in smart_results):
        print("\n[WARNING]  发现质量问题，建议修复后重新收集需求。")
        # Print fix suggestions for failed items
        functional = state.draft_content.get("P3", {}).get("functional", [])
        for result in smart_results:
            if not result.overall_pass:
                req = next((r for r in functional if r.get("id") == result.req_id), {})
                fix = suggest_fix(req, result)
                print(f"  [HINT] [{result.req_id}] {fix}")
        if not _ask_continue("是否继续生成PRD"):
            print("已取消。可重新运行工具修正需求。")
            return

    # Check Gherkin coverage
    coverage_gaps = _check_gherkin_coverage(state)
    if coverage_gaps:
        print(f"\n[WARNING]  Gherkin 覆盖缺口: {len(coverage_gaps)} 条 Must-Have 需求缺少对应场景")
        for req in coverage_gaps:
            print(f"    - {req.get('id', '')}: {req.get('text', '')[:50]}")

    # Final quality gate (ambiguity scan)
    ambiguity = _run_ambiguity_check(state, prd_text)
    if ambiguity["lexical"] or ambiguity["logic"] or ambiguity["completeness"]:
        report = format_quality_report(smart_results=[], ambiguity_result=ambiguity)
        print(report)
        if not _ask_continue("是否继续生成最终PRD"):
            print("已取消。可重新运行工具修正内容。")
            return

    # Save PRD to file
    if state.mode == "derive":
        parent_doc = state.draft_content["P1"].get("parent_doc", "unknown")
        module_name = state.draft_content["P1"].get("module_name", "unknown")
        version = state.draft_content["P1"].get("version", "1.0.0")
        output_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name}_prd_v{version}.md")
    else:
        project_name = state.draft_content["P1"].get("project_name", "unknown")
        version = state.draft_content["P1"].get("version", "1.0.0")
        output_path = Path(args.output) if args.output else Path(f"{project_name}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    new_session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, new_session_path)
    print(f"会话已保存至: {new_session_path}")


def run_root_mode(args: argparse.Namespace) -> None:
    """Run PRD generation in Root mode."""
    print("=" * 50)
    print("PRD Flow - Root Mode")
    print("=" * 50)

    state = SessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )

    # Phase 1: Frontmatter
    phase1 = FrontmatterPhase(state)
    phase1.run()
    print(f"\n生成文档ID: {state.draft_content['P1']['doc_id']}")

    # Phase 2: Problem Statement
    phase2 = ProblemStatementPhase(state)
    phase2.run()

    # Phase 3: Requirements (with quality gate)
    phase3 = RequirementsPhase(state)
    phase3.run()

    # Quality gate after P3
    smart_results = _run_smart_check(state)
    report = format_quality_report(smart_results=smart_results)
    print(report)

    if not all(r.overall_pass for r in smart_results):
        print("\n[WARNING]  发现质量问题，建议修复后重新收集需求。")
        # Print fix suggestions for failed items
        functional = state.draft_content.get("P3", {}).get("functional", [])
        for result in smart_results:
            if not result.overall_pass:
                req = next((r for r in functional if r.get("id") == result.req_id), {})
                fix = suggest_fix(req, result)
                print(f"  [HINT] [{result.req_id}] {fix}")
        if not _ask_continue("是否继续生成PRD"):
            print("已取消。可重新运行工具修正需求。")
            return

    # Check Gherkin coverage
    coverage_gaps = _check_gherkin_coverage(state)
    if coverage_gaps:
        print(f"\n[WARNING]  Gherkin 覆盖缺口: {len(coverage_gaps)} 条 Must-Have 需求缺少对应场景")
        for req in coverage_gaps:
            print(f"    - {req.get('id', '')}: {req.get('text', '')[:50]}")

    # Phase 4: Acceptance
    phase4 = AcceptancePhase(state)
    phase4.run()

    # Phase 5: Success Metrics
    phase5 = SuccessMetricsPhase(state)
    phase5.run()

    # Final assembly
    prd_text = assemble_prd(state.draft_content)

    # Final quality gate (ambiguity scan)
    ambiguity = _run_ambiguity_check(state, prd_text)
    if ambiguity["lexical"] or ambiguity["logic"] or ambiguity["completeness"]:
        report = format_quality_report(smart_results=[], ambiguity_result=ambiguity)
        print(report)
        if not _ask_continue("是否继续生成最终PRD"):
            print("已取消。可重新运行工具修正内容。")
            return

    # Save PRD to file
    project_name = state.draft_content["P1"].get("project_name", "unknown")
    version = state.draft_content["P1"].get("version", "1.0.0")
    output_path = Path(args.output) if args.output else Path(f"{project_name}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"会话已保存至: {session_path}")


def run_derive_mode(args: argparse.Namespace) -> int:
    """Run PRD generation in Derive mode (fully automated, no input() calls)."""
    print("=" * 50)
    print("PRD Flow - Derive Mode")
    print("=" * 50)

    # 1. Validate inputs
    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    target_granularity = getattr(args, "target_granularity", "auto") or "auto"
    if not args.parent_prd or not architecture_input or not args.target_module:
        print("Error: Derive mode requires --parent-prd, --architecture-package, and --target-module")
        return EXIT_INPUT_ERROR

    print(f"\nTarget module: {args.target_module}")
    print(f"Target granularity: {target_granularity}")
    print(f"Parent PRD: {args.parent_prd}")
    print(f"Architecture package: {architecture_input}")

    # 2. Parse parent documents
    target_module = args.target_module
    context = build_derive_context(
        Path(args.parent_prd),
        Path(architecture_input),
        target_module,
        target_granularity=target_granularity,
    )

    # 3. Auto-fix module name via edit distance matching
    if not context["success"]:
        similar = find_best_module_match(target_module, context.get("available_modules", []))
        if similar:
            target_module = similar
            context = build_derive_context(
                Path(args.parent_prd),
                Path(architecture_input),
                target_module,
                target_granularity=target_granularity,
            )
        if not context["success"]:
            print(context["error"])
            print("可用模块:")
            for mod in context.get("available_modules", []):
                print(f"  - {mod}")
            return EXIT_INPUT_ERROR

    module_name = context["module_name"]
    related_requirements = context.get("related_requirements", [])
    interfaces = context.get("interfaces", [])
    dependencies = context.get("dependencies", [])

    # 4. Auto-resolve orphan requirements (Option A: include with tentative=True)
    orphan_requirements = context.get("orphan_requirements", [])
    if orphan_requirements:
        print(f"\n注意: 发现 {len(orphan_requirements)} 条孤儿需求，自动纳入并标记为 tentative")
        resolved = resolve_orphan_requirements(orphan_requirements)
        related_requirements = related_requirements + resolved

    # 5. Log summary (no user confirmation needed)
    print(f"\n模块: {module_name}")
    print(f"相关需求: {len(related_requirements)} 条")
    print(f"接口: {len(interfaces)} 个")
    print(f"依赖: {len(dependencies)} 个")

    # 6. Initialize SessionState
    state = SessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        mode="derive",
        current_phase="D1",
        completed_phases=[],
        draft_content={},
        parent_context=context,
        target_module=target_module,
    )

    # D1: Frontmatter — auto-generate
    phase1 = FrontmatterPhase(state)
    phase1.collect_derive(
        parent_doc_id=context["parent_doc_id"],
        parent_arch_id=context.get("parent_arch_id"),
        module_name=module_name,
        interfaces=interfaces,
        dependencies=dependencies,
        priority="P0",
        author="Claude",
    )
    print(f"\n生成文档ID: {state.draft_content['P1']['doc_id']}")

    # Helper: clean requirement text (take first line only, strip markdown)
    def _clean_req_text(text: str) -> str:
        return text.split("\n")[0].strip().rstrip("-").strip()

    # D2: Problem Statement — auto-prefill from module context
    phase2 = ProblemStatementPhase(state)
    target_users = "系统用户"
    if related_requirements:
        first_req_text = _clean_req_text(related_requirements[0].get("text", ""))
        pain_points = f"当前系统在 {first_req_text} 方面存在能力不足"
    else:
        pain_points = "未明确"
    opportunity = f"由 {module_name} 模块统一封装能力，降低上层系统复杂度"
    phase2.collect(target_users=target_users, pain_points=pain_points, opportunity=opportunity)

    # D3: Requirements — for each related requirement, create 2 sub-reqs
    phase3 = RequirementsPhase(state)
    functional = []
    parent_reqs_for_fix = related_requirements  # used by fix_parent_req
    for req in related_requirements:
        req_id = req.get("id", "REQ-UNKNOWN")
        req_text = _clean_req_text(req.get("text", ""))
        is_tentative = req.get("tentative", False)
        parent_priority = req.get("priority", "Must Have")
        sub_req_1 = {
            "id": f"{req_id}-1",
            "text": f"{module_name} 应提供 {req_text} 的接口封装",
            "priority": parent_priority,
            "gherkin_count": 1,
            "parent_req": req_id,
        }
        sub_req_2 = {
            "id": f"{req_id}-2",
            "text": f"{module_name} 应实现 {req_text} 的核心逻辑",
            "priority": parent_priority,
            "gherkin_count": 1,
            "parent_req": req_id,
        }
        if is_tentative:
            sub_req_1["tentative"] = True
            sub_req_2["tentative"] = True
        # Apply auto-fixers
        sub_req_1 = fix_vague_quantifiers(sub_req_1)
        sub_req_1 = fix_measurable(sub_req_1)
        sub_req_1 = fix_parent_req(sub_req_1, parent_reqs_for_fix)

        sub_req_2 = fix_vague_quantifiers(sub_req_2)
        sub_req_2 = fix_measurable(sub_req_2)
        sub_req_2 = fix_parent_req(sub_req_2, parent_reqs_for_fix)

        functional.append(sub_req_1)
        functional.append(sub_req_2)

    non_functional = [{"id": "NFR-001", "text": f"模块 {module_name} 应符合上层架构约束"}]
    phase3.collect(functional=functional, non_functional=non_functional)

    # Quality gate after D3 — auto-fix failures
    smart_results = _run_smart_check(state)
    report = format_quality_report(smart_results=smart_results)
    print(report)

    if not all(r.overall_pass for r in smart_results):
        print("\n[WARNING]  发现质量问题，尝试自动修复...")
        functional = state.draft_content.get("P3", {}).get("functional", [])
        fixed_functional = []
        for req in functional:
            req = fix_vague_quantifiers(req)
            req = fix_measurable(req)
            req = fix_parent_req(req, parent_reqs_for_fix)
            fixed_functional.append(req)
        state.draft_content["P3"]["functional"] = fixed_functional

        # Re-check after auto-fix
        smart_results = _run_smart_check(state)
        if not all(r.overall_pass for r in smart_results):
            print("\n[ERROR] 自动修复后仍有质量问题:")
            errors = []
            for result in smart_results:
                if not result.overall_pass:
                    error_msg = f"[{result.req_id}] {', '.join(result.issues)}"
                    print(f"  - {error_msg}")
                    errors.append(error_msg)
            _write_error_report(state, errors, args)
            return EXIT_QUALITY_BLOCKED
        else:
            print("[OK] 自动修复后所有检查通过。")

    # Check Gherkin coverage — auto-fill for uncovered Must-Have
    coverage_gaps = _check_gherkin_coverage(state)
    if coverage_gaps:
        print(f"\n[WARNING]  Gherkin 覆盖缺口: {len(coverage_gaps)} 条 Must-Have 需求缺少对应场景，自动生成基础场景...")
        existing_scenarios = state.draft_content.get("P4", {}).get("scenarios", [])
        for req in coverage_gaps:
            req_id = req.get("id", "")
            req_text = req.get("text", "")
            existing_scenarios.append({
                "feature": module_name,
                "scenario": f"{req_id} 基础验证",
                "given": f"模块 {module_name} 正常运行",
                "when": f"执行 {req_text}",
                "then": "返回预期的成功响应",
            })
        if "P4" not in state.draft_content:
            state.draft_content["P4"] = {}
        state.draft_content["P4"]["scenarios"] = existing_scenarios
        # Update gherkin_count only on requirements that were in coverage gaps
        gap_ids = {req.get("id", "") for req in coverage_gaps}
        for req in functional:
            if req.get("id", "") in gap_ids:
                req["gherkin_count"] = req.get("gherkin_count", 0) + 1

    # D4: Acceptance — auto-generate from interfaces (2 scenarios per interface)
    phase4 = AcceptancePhase(state)
    scenarios = generate_interface_scenarios(module_name, interfaces)
    # Also include any auto-generated coverage scenarios
    if "P4" in state.draft_content and state.draft_content["P4"].get("scenarios"):
        scenarios = state.draft_content["P4"]["scenarios"] + scenarios
    phase4.collect(scenarios=scenarios)

    # D5: Success Metrics — auto-fill default metrics
    phase5 = SuccessMetricsPhase(state)
    metrics = [
        {"name": "接口响应时间", "target": "≤ 200ms", "method": "性能测试"},
        {"name": "接口可用性", "target": "≥ 99.9%", "method": "监控统计"},
    ]
    phase5.collect(metrics=metrics)

    # Final assembly
    prd_text = assemble_prd(state.draft_content)

    # Final ambiguity scan
    ambiguity = _run_ambiguity_check(state, prd_text)
    if ambiguity["logic"]:
        print("\n[ERROR] 发现逻辑冲突:")
        errors = []
        for item in ambiguity["logic"]:
            error_msg = f"[逻辑冲突] {item['description']}"
            print(f"  - {error_msg}")
            errors.append(error_msg)
        _write_error_report(state, errors, args)
        return EXIT_QUALITY_BLOCKED

    # Save output
    parent_doc = state.draft_content["P1"].get("parent_doc", "unknown")
    module_name_out = state.draft_content["P1"].get("module_name", "unknown")
    version = state.draft_content["P1"].get("version", "1.0.0")
    output_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name_out}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    print(f"\nPRD已保存至: {output_path}")

    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"会话已保存至: {session_path}")

    return EXIT_SUCCESS


def _select_mode_interactive(args: argparse.Namespace) -> Mode:
    """交互式选择运行模式。如果命令行已提供derive参数则自动推断。"""
    # Shortcut: all derive inputs present -> skip question
    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    if args.parent_prd and architecture_input and args.target_module:
        return Mode.DERIVE

    print("=" * 50)
    print("PRD Flow - 产品需求文档生成工具")
    print("=" * 50)
    print("\n请选择模式:")
    print("  [1] Root 模式 — 从零创建新的顶层 PRD")
    print("  [2] Derive 模式 — 基于已有 PRD 派生模块级 PRD")

    while True:
        choice = input("\n请输入 (1/2): ").strip()
        if choice == "1":
            return Mode.ROOT
        elif choice == "2":
            return Mode.DERIVE
        else:
            print("[WARNING]  无效输入，请输入 1 或 2")


def _prompt_derive_inputs(args: argparse.Namespace) -> argparse.Namespace:
    """Derive 模式下交互式补全缺失的输入参数。"""
    print("\n--- Derive 模式配置 ---")

    if not args.parent_prd:
        args.parent_prd = input("父 PRD 文件路径: ").strip()
    else:
        print(f"父 PRD 文件路径: {args.parent_prd}")

    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    if not architecture_input:
        args.architecture_package = input("架构包路径（目录、README.md 或 zip）: ").strip()
    else:
        print(f"架构包路径: {architecture_input}")

    if not args.target_module:
        args.target_module = input("目标模块名称: ").strip()
    else:
        print(f"目标模块名称: {args.target_module}")

    if not args.output:
        default_output = f"{args.target_module}_prd.md"
        out = input(f"输出文件路径 [默认: {default_output}]: ").strip()
        args.output = out if out else default_output
    else:
        print(f"输出文件路径: {args.output}")

    return args


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PRD Flow - Interactive PRD generation")
    parser.add_argument("--parent-prd", help="Path to parent PRD document")
    parser.add_argument("--architecture-package", help="Path to architecture package directory, README.md, or zip")
    parser.add_argument("--parent-architecture", help="Legacy alias for --architecture-package")
    parser.add_argument("--target-module", help="Target module name for Derive mode")
    parser.add_argument(
        "--target-granularity",
        choices=["auto", "deployable_module", "bounded_context"],
        default="auto",
        help="Target level for Derive mode",
    )
    parser.add_argument("--resume", help="Path to session file to resume")
    parser.add_argument("--output", "-o", help="输出PRD文件路径")

    args = parser.parse_args(argv)

    if args.resume:
        _resume_session(Path(args.resume), args)
        return EXIT_SUCCESS

    # Interactive mode selection
    mode = _select_mode_interactive(args)

    if mode == Mode.DERIVE:
        args = _prompt_derive_inputs(args)
        return run_derive_mode(args)
    else:
        run_root_mode(args)
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
