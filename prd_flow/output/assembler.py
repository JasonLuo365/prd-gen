"""Assemble the complete three-phase PRD document."""
from prd_flow.output.formatter import (
    format_acceptance,
    format_frontmatter,
    format_problem_statement,
    format_requirements,
    format_success_metrics,
)


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

    # Phase 4: Acceptance (Gherkin)
    p4_data = draft_content.get("P4", {})
    if p4_data:
        parts.append(format_acceptance(p4_data))
        parts.append("")

    # Phase 5: Success Metrics
    p5_data = draft_content.get("P5", {})
    if p5_data:
        parts.append(format_success_metrics(p5_data))

    return "\n".join(parts)
