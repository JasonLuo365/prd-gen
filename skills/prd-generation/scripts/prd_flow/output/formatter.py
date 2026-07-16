"""Format PRD sections using the PRD-to-Gherkin handoff contract."""
from prd_flow import yaml_utils as yaml
from prd_flow.quality.oracle import build_coverage_ledger, release_scope


def format_frontmatter(data: dict) -> str:
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def format_problem_statement(data: dict) -> str:
    return "\n".join(["# Problem Statement\n", "## 目标用户", data.get("target_users", "[待填写]"), "\n## 痛点描述", data.get("pain_points", "[待填写]"), "\n## 机会窗口", data.get("opportunity", "[待填写]")])


def _metadata(lines: list[str], item: dict) -> None:
    lines.append(f"  - release_scope: {release_scope(item)}")
    lines.append(f"  - requirement_kind: {item.get('requirement_kind', 'atomic')}")
    for key in ("parent_req", "parent_nfr", "source_kind"):
        if item.get(key):
            lines.append(f"  - {key}: {item[key]}")
    for key in ("implementation_surfaces", "related_reqs", "evidence_refs"):
        if item.get(key):
            lines.append(f"  - {key}: [{', '.join(item[key])}]")


def format_requirements(data: dict) -> str:
    lines = ["# Requirements\n", "## Current Release — Functional Requirements\n"]
    current = [r for r in data.get("functional", []) if release_scope(r) == "current"]
    for priority in ("Must Have", "Should Have", "Could Have"):
        reqs = [r for r in current if r.get("priority", "Must Have") == priority]
        if reqs:
            lines.append(f"### {priority}")
            for req in reqs:
                lines.append(f'- [{req["id"]}] {req["text"]}')
                _metadata(lines, req)
            lines.append("")
    lines.append("## Current Release — Non-functional Requirements")
    for nfr in data.get("non_functional", []):
        if release_scope(nfr) == "current":
            lines.append(f'- [{nfr["id"]}] {nfr["text"]}')
            _metadata(lines, nfr)
    excluded = [*(r for r in data.get("functional", []) if release_scope(r) != "current"), *(r for r in data.get("non_functional", []) if release_scope(r) != "current")]
    if excluded:
        lines.extend(["", "## Future Backlog / Documented Exclusions", "", "本节不是当前版本的规范性需求。", ""])
        for item in excluded:
            lines.append(f'- [{item["id"]}] {item["text"]}')
            _metadata(lines, item)
            if item.get("scope_reason"):
                lines.append(f'  - scope_reason: {item["scope_reason"]}')
    if data.get("non_goals"):
        lines.extend(["", "## Non-goals"])
        lines.extend(f"- {item}" for item in data["non_goals"])
    return "\n".join(lines)


def _value(value: object) -> str:
    if isinstance(value, list):
        rendered = []
        for item in value:
            if isinstance(item, dict) and item.get("condition") and item.get("response"):
                rendered.append(f"{item['condition']} -> {item['response']}")
            else:
                rendered.append(str(item))
        return " | ".join(rendered)
    return str(value or "")


def format_acceptance(data: dict, requirements: dict | None = None) -> str:
    """Format source oracles, never Gherkin scenarios or test cases."""
    contracts = data.get("contracts", [])
    lines = ["# Acceptance Contracts\n", "> 本节定义业务判定依据；不包含测试用例或 Gherkin。下游只能据此展开测试技术。", ""]
    fields = ("actor", "preconditions", "trigger", "response", "observable_oracles", "boundaries", "exceptions", "population", "measurement_start", "measurement_end", "unit", "threshold", "exclusions", "pass_rule", "evidence_refs")
    for contract in contracts:
        contract_id = contract.get("id") or contract.get("ac_id", "UNKNOWN")
        verifies = contract.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        lines.extend([f"## {contract_id}", f"- type: {contract.get('type', 'functional')}", f"- verifies: [{', '.join(verifies)}]", f"- release_scope: {release_scope(contract)}"])
        for field in fields:
            if field in contract:
                lines.append(f"- {field}: {_value(contract[field])}")
        lines.append("")
    if requirements is not None:
        lines.extend(["## Oracle Coverage Ledger", "", "| Requirement | Type | Release scope | Acceptance Contract | Status | Reason |", "|---|---|---|---|---|---|"])
        for row in build_coverage_ledger(requirements, contracts):
            lines.append(f"| {row['requirement_id']} | {row['type']} | {row['release_scope']} | {', '.join(row['contract_ids']) or '-'} | {row['status']} | {row['reason'] or '-'} |")
    return "\n".join(lines)


def format_success_metrics(data: dict) -> str:
    lines = ["# Success Metrics\n", "| ID | Metric | Target | Measurement | Verifies |", "|---|---|---|---|---|"]
    for index, metric in enumerate(data.get("metrics", []), start=1):
        lines.append(f"| {metric.get('id', f'METRIC-{index:03d}')} | {metric.get('name', '')} | {metric.get('target', '')} | {metric.get('method', '')} | {', '.join(metric.get('verifies', [])) or '-'} |")
    return "\n".join(lines)
