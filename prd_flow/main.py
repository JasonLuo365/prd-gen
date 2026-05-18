"""Main CLI entry point for PRD Flow."""
from __future__ import annotations

import argparse
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
from prd_flow.session import SessionState, save_session


def _run_smart_check(state: SessionState) -> list:
    """对P3的功能需求运行SMART-REQ检查。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return [check_smart_req(req) for req in functional]


def _run_ambiguity_check(state: SessionState, prd_text: str) -> dict:
    """对PRD文本运行歧义扫描。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return scan_ambiguity(prd_text, functional)


def _ask_continue(prompt: str) -> bool:
    """询问用户是否继续。"""
    answer = input(f"{prompt} (y/n): ").strip().lower()
    return answer in ("y", "yes", "是")


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
        print("\n⚠️  发现质量问题，建议修复后重新收集需求。")
        if not _ask_continue("是否继续生成PRD"):
            print("已取消。可重新运行工具修正需求。")
            return

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
    output_path = Path(args.output) if args.output else Path(f"{state.draft_content['P1']['doc_id']}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"会话已保存至: {session_path}")


def run_derive_mode(args: argparse.Namespace) -> None:
    """Run PRD generation in Derive mode."""
    print("=" * 50)
    print("PRD Flow - Derive Mode")
    print("=" * 50)

    if not args.parent_prd or not args.parent_architecture or not args.target_module:
        print("Error: Derive mode requires --parent-prd, --parent-architecture, and --target-module")
        sys.exit(1)

    print(f"\nTarget module: {args.target_module}")
    print(f"Parent PRD: {args.parent_prd}")
    print(f"Parent Architecture: {args.parent_architecture}")

    # Full implementation would parse parent docs and pre-fill context
    print("\nDerive mode skeleton complete.")


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PRD Flow - Interactive PRD generation")
    parser.add_argument("--parent-prd", help="Path to parent PRD document")
    parser.add_argument("--parent-architecture", help="Path to parent architecture document")
    parser.add_argument("--target-module", help="Target module name for Derive mode")
    parser.add_argument("--resume", help="Path to session file to resume")
    parser.add_argument("--output", "-o", help="输出PRD文件路径")

    args = parser.parse_args(argv)

    # Detect mode from arguments
    mode = detect_mode(
        user_input=" ".join(sys.argv),
        parent_prd=args.parent_prd,
        parent_architecture=args.parent_architecture,
        target_module=args.target_module,
    )

    if mode == Mode.DERIVE:
        run_derive_mode(args)
    else:
        run_root_mode(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
