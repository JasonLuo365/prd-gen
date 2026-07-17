"""Assemble the complete three-phase PRD document."""
from prd_flow.output.formatter import (
    format_acceptance,
    format_architecture_input,
    format_frontmatter,
    format_problem_statement,
    format_requirements,
    format_success_metrics,
)
from prd_flow.quality.oracle import check_oracle_coverage


def assemble_prd(draft_content: dict) -> str:
    """Assemble a complete PRD from draft content.

    Args:
        draft_content: Dict mapping phase IDs to collected data.

    Returns:
        Complete PRD document as a string.
    """
    parts = []

    # Phase 1: Frontmatter (YAML)
    p1_data = draft_content.get("P1", {})
    if p1_data:
        p1_data = dict(p1_data)
        oracle_gaps = check_oracle_coverage(
            draft_content.get("P3", {}),
            draft_content.get("P4", {}).get("contracts", []),
        )
        p1_data.setdefault("doc_type", "prd")
        p1_data.setdefault("schema_version", "2.0")
        scopes_resolved = not any(
            item.get("release_scope", "current") == "unknown"
            for item in [
                *draft_content.get("P3", {}).get("functional", []),
                *draft_content.get("P3", {}).get("non_functional", []),
            ]
        )
        p1_data["release_scope_frozen"] = bool(p1_data.get("release_scope_frozen", False)) and scopes_resolved
        p1_data["oracle_blocked_count"] = len(oracle_gaps)
        if p1_data.get("layer") == "derive":
            p1_data["status"] = "complete"
            p1_data["ready_for_test_generation"] = bool(
                p1_data.get("inheritance_complete", False)
            ) and not oracle_gaps
            p1_data["review_method"] = "inheritance_allocation_gate"
            p1_data.pop("agent_review_passed", None)
        else:
            p1_data["ready_for_test_generation"] = (
                p1_data["release_scope_frozen"]
                and not oracle_gaps
                and bool(p1_data.get("agent_review_passed", False))
            )
            p1_data["review_method"] = "independent_agent"
        parts.append("---")
        parts.append(format_frontmatter(p1_data).strip())
        parts.append("---\n")

    # Phase 2: Problem Statement
    p2_data = draft_content.get("P2", {})
    if p2_data:
        parts.append(format_problem_statement(p2_data))
        parts.append("")

    # Phase 3: Requirements
    p3_data = draft_content.get("P3", {})
    if p3_data:
        parts.append(format_requirements(p3_data))
        parts.append("")

    # 架构约束放在产品需求和 NFR 之后，且不转化为规范性产品需求。
    parts.append(format_architecture_input(draft_content.get("P6", {})))
    parts.append("")

    # Phase 5: Success Metrics
    p5_data = draft_content.get("P5", {})
    if p5_data:
        parts.append(format_success_metrics(p5_data))
        parts.append("")

    # Phase 4: Acceptance Contracts (business oracles; never Gherkin)
    p4_data = draft_content.get("P4", {})
    if p4_data:
        parts.append(format_acceptance(p4_data, p3_data))

    return "\n".join(parts)
