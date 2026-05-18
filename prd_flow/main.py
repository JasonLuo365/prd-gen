"""Main CLI entry point for PRD Flow."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prd_flow.mode_detector import Mode, detect_mode
from prd_flow.output.assembler import assemble_prd
from prd_flow.quality.smart_req import check_smart_req
from prd_flow.session import SessionState, save_session


def generate_doc_id(project_name: str) -> str:
    """Generate document ID from project name."""
    base = project_name.upper().replace(" ", "-").replace("_", "-")
    return f"{base}-v1.0"


def run_root_mode(args: argparse.Namespace) -> None:
    """Run PRD generation in Root mode."""
    print("=" * 50)
    print("PRD Flow - Root Mode")
    print("=" * 50)

    state = SessionState(
        session_id=f"sess_{Path(__file__).stem}",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )

    # Phase 1: Frontmatter
    print("\n[Phase 1/5] Frontmatter - Document Metadata")
    project_name = input("Project name: ").strip()
    author = input("Author (default: Claude): ").strip() or "Claude"
    priority = input("Priority (P0/P1/P2, default: P0): ").strip() or "P0"

    state.draft_content["P1"] = {
        "doc_id": generate_doc_id(project_name),
        "version": "1.0.0",
        "layer": "root",
        "parent_doc": None,
        "author": author,
        "status": "draft",
        "priority": priority,
    }

    print(f"\nGenerated doc_id: {state.draft_content['P1']['doc_id']}")

    # Save session after each phase
    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"Session saved to: {session_path}")

    # Note: Phases 2-5 would follow similar interactive patterns
    # For brevity, we demonstrate the structure; full implementation
    # would include all five phases with quality checks

    print("\n" + "=" * 50)
    print("Root mode skeleton complete.")
    print("Full interactive flow implemented in phases/ modules.")
    print("=" * 50)


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
