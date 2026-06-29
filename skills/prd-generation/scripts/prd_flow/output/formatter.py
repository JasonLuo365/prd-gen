"""Format individual sections of the PRD document."""

from prd_flow import yaml_utils as yaml


def format_frontmatter(data: dict) -> str:
    """Format frontmatter as YAML."""
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def format_problem_statement(data: dict) -> str:
    """Format Problem Statement section."""
    lines = ["# Problem Statement\n"]
    lines.append("## 目标用户")
    lines.append(data.get("target_users", "[待填写]"))
    lines.append("\n## 痛点描述")
    lines.append(data.get("pain_points", "[待填写]"))
    lines.append("\n## 机会窗口")
    lines.append(data.get("opportunity", "[待填写]"))
    return "\n".join(lines)


def format_requirements(data: dict) -> str:
    """Format Requirements section."""
    lines = ["# Requirements\n"]
    lines.append("## 功能需求\n")

    by_priority = {"Must Have": [], "Should Have": [], "Could Have": []}
    for req in data.get("functional", []):
        priority = req.get("priority", "Must Have")
        by_priority.setdefault(priority, []).append(req)

    for priority in ["Must Have", "Should Have", "Could Have"]:
        reqs = by_priority.get(priority, [])
        if reqs:
            lines.append(f"### {priority}")
            for req in reqs:
                lines.append(f'- [{req["id"]}] {req["text"]}')
                if req.get("parent_req"):
                    lines.append(f'  - parent_req: {req["parent_req"]}')
            lines.append("")

    lines.append("## 非功能需求")
    for nfr in data.get("non_functional", []):
        lines.append(f'- [{nfr["id"]}] {nfr["text"]}')

    return "\n".join(lines)


def format_acceptance(data: dict) -> str:
    """Format Acceptance section with Gherkin."""
    lines = ["# Acceptance\n", "```gherkin"]

    for sc in data.get("scenarios", []):
        lines.append(f'Feature: {sc.get("feature", "")}')
        lines.append(f'  Scenario: {sc.get("scenario", "")}')
        lines.append(f'    Given {sc.get("given", "")}')
        lines.append(f'    When {sc.get("when", "")}')
        for and_step in sc.get("and_steps", []):
            lines.append(f'    And {and_step}')
        lines.append(f'    Then {sc.get("then", "")}')
        lines.append("")

    lines.append("```")
    return "\n".join(lines)


def format_success_metrics(data: dict) -> str:
    """Format Success Metrics section."""
    lines = ["# Success Metrics\n"]
    lines.append("| 指标 | 目标值 | 测量方式 |")
    lines.append("|:---|:---|:---|")

    for metric in data.get("metrics", []):
        lines.append(f'| {metric["name"]} | {metric["target"]} | {metric["method"]} |')

    return "\n".join(lines)
