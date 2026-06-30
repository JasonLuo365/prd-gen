#!/usr/bin/env python3
"""Static checker for the leaf-gate skill.

The script intentionally uses only Python standard library modules so it can run
inside most Codex workspaces without installing dependencies. It performs
deterministic checks only; semantic judgement still belongs to the LLM judge.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_THRESHOLDS = {
    "max_scenario_points": 10,
    "max_expanded_cases": 20,
    "max_steps_per_scenario": 12,
    "max_req_tags_per_scenario": 3,
    "max_open_questions": 0,
    "max_high_risks": 0,
    "max_estimated_tokens": 24000,
    "min_llm_confidence": 0.75,
}

CRITERIA = [
    "C1_behavior_complexity",
    "C2_contract_boundary",
    "C3_ai_context_control",
    "C4_verifiability",
    "C5_risk_decomposition",
]


@dataclass
class ArtifactSet:
    node_dir: Path
    prd: Optional[Path]
    feature: Optional[Path]
    architecture: Optional[Path]
    traceability: Optional[Path]
    risks: Optional[Path]
    architecture_files: List[Path] = field(default_factory=list)
    architecture_validation: Optional[Path] = None


def read_text(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_texts(paths: Iterable[Path]) -> str:
    chunks = []
    for path in paths:
        text = read_text(path)
        if text:
            chunks.append(f"\n\n<!-- source: {path.name} -->\n{text}")
    return "\n".join(chunks)


def find_first(node_dir: Path, names: Iterable[str], patterns: Iterable[str]) -> Optional[Path]:
    for name in names:
        candidate = node_dir / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for pattern in patterns:
        matches = sorted(node_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def markdown_files(path: Path) -> List[Path]:
    return sorted(file for file in path.glob("*.md") if file.is_file())


def find_architecture_artifacts(node_dir: Path) -> Tuple[Optional[Path], List[Path], Optional[Path]]:
    architecture_file = find_first(
        node_dir,
        ["architecture.yaml", "architecture.yml", "architecture.json", "architecture.md"],
        ["*architecture*.yaml", "*architecture*.yml", "*architecture*.json", "*architecture*.md", "*arch*.md"],
    )
    if architecture_file:
        return architecture_file, [architecture_file], None

    architecture_dir = node_dir / "architecture"
    if not architecture_dir.exists() or not architecture_dir.is_dir():
        return None, [], None

    output_dir = architecture_dir / "output"
    if output_dir.exists() and output_dir.is_dir():
        files = markdown_files(output_dir)
        validation = architecture_dir / "validation-report.md"
        if validation.exists() and validation.is_file():
            files.append(validation)
        return output_dir, files, validation if validation.exists() else None

    files = markdown_files(architecture_dir)
    validation = architecture_dir / "validation-report.md"
    return architecture_dir, files, validation if validation.exists() else None


def find_artifacts(node_dir: Path) -> ArtifactSet:
    architecture, architecture_files, architecture_validation = find_architecture_artifacts(node_dir)
    return ArtifactSet(
        node_dir=node_dir,
        prd=find_first(node_dir, ["prd.md", "PRD.md"], ["*prd*.md", "*PRD*.md"]),
        feature=find_first(node_dir, ["testcase.feature"], ["*.feature"]),
        architecture=architecture,
        traceability=find_first(
            node_dir,
            ["traceability.yaml", "traceability.yml", "traceability.json", "traceability.md"],
            ["*traceability*.yaml", "*traceability*.yml", "*traceability*.json", "*traceability*.md", "*mapping*.md"],
        ),
        risks=find_first(
            node_dir,
            ["risks.yaml", "risks.yml", "risks.json", "risks.md", "risk_register.md"],
            ["*risk*.yaml", "*risk*.yml", "*risk*.json", "*risk*.md"],
        ),
        architecture_files=architecture_files,
        architecture_validation=architecture_validation,
    )


def status(level: str, reason: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": level,
        "reason": reason,
        "evidence": evidence or {},
    }


def count_requirements(prd_text: str) -> List[str]:
    return sorted(set(re.findall(r"\b(?:REQ|NFR)-\d{3,}\b", prd_text)))


def extract_requirements(prd_text: str) -> List[Dict[str, str]]:
    requirements: Dict[str, Dict[str, str]] = {}
    section = ""
    for line in prd_text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1)
        for req_id in re.findall(r"\b(?:REQ|NFR)-\d{3,}\b", line):
            clean = re.sub(r"^\s*[-*]\s*", "", line).strip()
            clean = re.sub(rf"^\[?{re.escape(req_id)}\]?\s*", "", clean).strip()
            clean = clean or line.strip()
            requirements.setdefault(req_id, {"id": req_id, "text": clean, "section": section})
    return [requirements[req_id] for req_id in sorted(requirements)]


def count_open_questions(prd_text: str) -> int:
    marker = re.search(r"(?im)^##\s+Open Questions\s*$", prd_text)
    if not marker:
        return 0
    section = prd_text[marker.end() :]
    next_heading = re.search(r"(?m)^##\s+", section)
    if next_heading:
        section = section[: next_heading.start()]
    bullets = re.findall(r"(?m)^\s*[-*]\s+\S+", section)
    return len(bullets)


def count_todos(*texts: str) -> int:
    combined = "\n".join(texts)
    return len(re.findall(r"\b(?:TODO|TBD|FIXME|待定|未定|待补充|待明确)\b", combined, flags=re.IGNORECASE))


def parse_feature(feature_text: str) -> Dict[str, Any]:
    scenario_re = re.compile(r"^\s*Scenario(?:\s+Outline)?:\s*(.+?)\s*$", re.MULTILINE)
    tag_re = re.compile(r"@\S+")
    step_re = re.compile(r"^\s*(Given|When|Then|And|But)\b", re.MULTILINE)

    scenarios: List[Dict[str, Any]] = []
    matches = list(scenario_re.finditer(feature_text))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(feature_text)
        block = feature_text[start:end]
        prefix_start = max(0, feature_text.rfind("\n\n", 0, start))
        prefix = feature_text[prefix_start:start]
        tags = tag_re.findall(prefix)
        req_tags = sorted(set(tag[1:] for tag in tags if re.match(r"@(?:REQ|NFR)-\d{3,}", tag)))
        trace_tags = sorted(set(tag[1:] for tag in tags if re.match(r"@(?:REQ|NFR|MET)-\d{3,}", tag)))
        steps = step_re.findall(block)
        example_rows = 0
        if "Scenario Outline" in match.group(0):
            table_rows = re.findall(r"(?m)^\s*\|.+\|\s*$", block)
            example_rows = max(0, len(table_rows) - 1)
        scenarios.append(
            {
                "name": match.group(1),
                "outline": "Scenario Outline" in match.group(0),
                "tags": tags,
                "req_tags": req_tags,
                "trace_tags": trace_tags,
                "step_count": len(steps),
                "example_rows": example_rows,
            }
        )

    scenario_count = len(scenarios)
    outline_count = sum(1 for item in scenarios if item["outline"])
    expanded_case_count = sum(max(1, item["example_rows"]) for item in scenarios)
    max_steps = max((item["step_count"] for item in scenarios), default=0)
    max_req_tags = max((len(item["req_tags"]) for item in scenarios), default=0)
    untagged = [item["name"] for item in scenarios if not item["trace_tags"]]
    covered_reqs = sorted({tag for item in scenarios for tag in item["req_tags"]})

    return {
        "scenario_count": scenario_count,
        "scenario_outline_count": outline_count,
        "expanded_case_count": expanded_case_count,
        "max_steps_per_scenario": max_steps,
        "max_req_tags_per_scenario": max_req_tags,
        "untagged_scenarios": untagged,
        "covered_requirements": covered_reqs,
        "scenarios": scenarios,
    }


def scenario_map(feature: Dict[str, Any]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    for scenario in feature["scenarios"]:
        for req_id in scenario["req_tags"]:
            mapping.setdefault(req_id, []).append(str(scenario["name"]))
    return mapping


def detect_deferred_requirements(prd_text: str, feature_text: str) -> set[str]:
    deferred: set[str] = set()
    for line in feature_text.splitlines():
        if re.search(r"deferred|延期|未进入|缺少确定|未冻结|不生成", line, flags=re.IGNORECASE):
            deferred.update(re.findall(r"\b(?:REQ|NFR)-\d{3,}\b", line))

    in_could_have = False
    for line in prd_text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            in_could_have = "could have" in title
            continue
        if in_could_have:
            deferred.update(re.findall(r"\b(?:REQ|NFR)-\d{3,}\b", line))
    return deferred


def relative_to_node(path: Path, node_dir: Path) -> str:
    try:
        return str(path.relative_to(node_dir)).replace("\\", "/")
    except ValueError:
        return str(path)


def architecture_evidence(req_id: str, architecture_files: Iterable[Path], node_dir: Path) -> List[str]:
    evidence = []
    for path in architecture_files:
        if req_id in read_text(path):
            evidence.append(relative_to_node(path, node_dir))
    return evidence


def build_traceability_text(artifacts: ArtifactSet) -> str:
    prd_text = read_text(artifacts.prd)
    feature_text = read_text(artifacts.feature)
    feature = parse_feature(feature_text)
    scenarios_by_req = scenario_map(feature)
    deferred = detect_deferred_requirements(prd_text, feature_text)
    rows = []
    for requirement in extract_requirements(prd_text):
        req_id = requirement["id"]
        scenarios = scenarios_by_req.get(req_id, [])
        evidence = architecture_evidence(req_id, artifacts.architecture_files, artifacts.node_dir)
        if scenarios and evidence:
            status_value = "covered"
        elif req_id in deferred:
            status_value = "deferred"
        elif not scenarios:
            status_value = "missing_testcase"
        elif not evidence:
            status_value = "missing_architecture"
        else:
            status_value = "covered"
        rows.append(
            "| {req_id} | {text} | {scenarios} | {evidence} | {status} |".format(
                req_id=req_id,
                text=requirement["text"].replace("|", "\\|"),
                scenarios=", ".join(scenarios) if scenarios else "none",
                evidence=", ".join(evidence) if evidence else "none",
                status=status_value,
            )
        )

    return "\n".join(
        [
            "# Traceability",
            "",
            "> Generated by Leaf Gate prepare evidence from the current node PRD, testcase, and architecture package.",
            "",
            "| Requirement | Requirement text | Testcase scenarios | Architecture evidence | Status |",
            "| --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def parse_traceability_inactive_requirements(traceability_text: str) -> set[str]:
    inactive = set()
    for line in traceability_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        lowered = line.lower()
        if "deferred" not in lowered and "excluded" not in lowered and "not_applicable" not in lowered:
            continue
        inactive.update(re.findall(r"\b(?:REQ|NFR)-\d{3,}\b", line))
    return inactive


def extract_validation_risk_rows(architecture_files: Iterable[Path], node_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in architecture_files:
        text = read_text(path)
        in_risk_section = False
        for line in text.splitlines():
            heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
            if heading:
                title = heading.group(1)
                if re.search(r"risk|风险|缓解", title, flags=re.IGNORECASE):
                    in_risk_section = True
                    continue
                if in_risk_section:
                    break
            if not in_risk_section or not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[0] in {"风险", "Risk"} or set(cells[0]) <= {"-"}:
                continue
            rows.append(
                {
                    "risk": cells[0],
                    "impact": cells[1],
                    "mitigation": cells[2],
                    "evidence": relative_to_node(path, node_dir),
                }
            )
    return rows


def build_risks_text(artifacts: ArtifactSet) -> str:
    traceability_text = build_traceability_text(artifacts)
    rows = []
    for item in extract_validation_risk_rows(artifacts.architecture_files, artifacts.node_dir):
        mitigation = item["mitigation"]
        status_value = "open" if re.search(r"未来|待|未|TODO|TBD", mitigation, flags=re.IGNORECASE) else "mitigated"
        severity = "high" if re.search(r"高风险|不可逆|删除|合规", item["risk"]) else "medium"
        rows.append(
            "| {risk} | {impact} | {severity} | {status} | {mitigation} | {evidence} |".format(
                risk=item["risk"].replace("|", "\\|"),
                impact=item["impact"].replace("|", "\\|"),
                severity=severity,
                status=status_value,
                mitigation=mitigation.replace("|", "\\|"),
                evidence=item["evidence"],
            )
        )

    for line in traceability_text.splitlines():
        if not line.lstrip().startswith("|") or "missing_" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        rows.append(
            "| Coverage gap for {req_id} | Automatic verification may be incomplete | high | open | Add missing testcase or architecture evidence before Leaf Gate can pass | traceability.md |".format(
                req_id=cells[0]
            )
        )

    if not rows:
        rows.append("| No identified residual risk | Current evidence has no explicit risk rows. | low | accepted | n/a | generated |")

    return "\n".join(
        [
            "# Risks",
            "",
            "> Generated by Leaf Gate prepare evidence from traceability gaps and architecture validation evidence.",
            "",
            "| Risk | Impact | Severity | Status | Mitigation | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
            "",
        ]
    )


def prepare_evidence(artifacts: ArtifactSet) -> ArtifactSet:
    if artifacts.prd and artifacts.feature:
        (artifacts.node_dir / "traceability.md").write_text(build_traceability_text(artifacts), encoding="utf-8")
        (artifacts.node_dir / "risks.md").write_text(build_risks_text(artifacts), encoding="utf-8")
    return find_artifacts(artifacts.node_dir)


def contract_fields(architecture_text: str) -> Dict[str, bool]:
    aliases = {
        "inputs": [r"\binputs?\b", r"\brequest\b", "输入", "入参", "请求"],
        "outputs": [r"\boutputs?\b", r"\bresponse\b", "输出", "响应", "返回"],
        "errors": [r"\berrors?\b", r"\bfailure\b", "错误", "异常", "错误码", "失败"],
        "states": [r"\bstates?\b", r"\btransition\b", "状态", "状态机", "流转"],
        "side_effects": [r"\bside effects?\b", r"\beffects?\b", "副作用", "持久化", "写入", "发送", "操作"],
        "dependencies": [r"\bdependencies\b", r"\bdepends on\b", "依赖", "外部系统", "调用"],
    }
    found: Dict[str, bool] = {}
    for field, patterns in aliases.items():
        found[field] = any(re.search(pattern, architecture_text, flags=re.IGNORECASE) for pattern in patterns)
    return found


def risk_counts(risk_text: str) -> Dict[str, int]:
    high_patterns = [
        r"\bhigh\b.*\b(open|unresolved|active)\b",
        r"\b(open|unresolved|active)\b.*\bhigh\b",
        r"高风险.*(未解决|开放|待定|active|open)",
        r"(未解决|开放|待定).*高风险",
    ]
    negated_high_patterns = [
        r"\b(no|none|zero)\b.*\b(open|unresolved|active)\b.*\b(high|risk)",
        r"\b(no|none|zero)\b.*\bhigh\b.*\b(open|unresolved|active)\b",
        r"(无|没有|不存在).*(未解决|开放|待定).*高风险",
        r"(无|没有|不存在).*高风险.*(未解决|开放|待定)",
    ]
    high_unresolved = 0
    for line in risk_text.splitlines():
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in negated_high_patterns):
            continue
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in high_patterns):
            high_unresolved += 1
    return {
        "unresolved_high_risks": high_unresolved,
        "risk_like_lines": len(re.findall(r"(?im)\b(risk|风险)\b", risk_text)),
    }


def estimate_tokens(*texts: str) -> int:
    # Mixed Chinese/English approximation: characters/3 is safer than words/0.75.
    chars = sum(len(text) for text in texts)
    return int(chars / 3) if chars else 0


def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists() or path.suffix.lower() != ".json":
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def static_checks(artifacts: ArtifactSet, thresholds: Dict[str, Any]) -> Dict[str, Any]:
    prd_text = read_text(artifacts.prd)
    feature_text = read_text(artifacts.feature)
    architecture_text = read_texts(artifacts.architecture_files) if artifacts.architecture_files else read_text(artifacts.architecture)
    traceability_text = read_text(artifacts.traceability)
    risk_text = read_text(artifacts.risks)

    requirements = count_requirements(prd_text)
    feature = parse_feature(feature_text) if feature_text else parse_feature("")
    fields = contract_fields(architecture_text)
    missing_fields = [name for name, present in fields.items() if not present]
    risks = risk_counts(risk_text)
    token_estimate = estimate_tokens(prd_text, feature_text, architecture_text, traceability_text, risk_text)
    open_questions = count_open_questions(prd_text)
    todos = count_todos(prd_text, feature_text, architecture_text, traceability_text, risk_text)

    missing_artifacts = [
        name
        for name, path in {
            "prd": artifacts.prd,
            "feature": artifacts.feature,
            "architecture": artifacts.architecture,
            "traceability": artifacts.traceability,
            "risks": artifacts.risks,
        }.items()
        if path is None
    ]

    c1_failures = []
    if not artifacts.feature:
        c1_failures.append("missing testcase.feature")
    if feature["scenario_count"] == 0:
        c1_failures.append("no scenarios found")
    if feature["expanded_case_count"] > thresholds["max_expanded_cases"]:
        c1_failures.append("expanded case count exceeds threshold")
    if feature["max_steps_per_scenario"] > thresholds["max_steps_per_scenario"]:
        c1_failures.append("max steps per scenario exceeds threshold")
    if feature["max_req_tags_per_scenario"] > thresholds["max_req_tags_per_scenario"]:
        c1_failures.append("scenario maps to too many requirements")

    c2_failures = []
    if not artifacts.architecture:
        c2_failures.append("missing architecture artifact")
    if missing_fields:
        c2_failures.append("missing contract fields")

    c3_failures = []
    if token_estimate > thresholds["max_estimated_tokens"]:
        c3_failures.append("estimated context exceeds threshold")
    if open_questions > thresholds["max_open_questions"]:
        c3_failures.append("open questions exceed threshold")
    if todos:
        c3_failures.append("TODO/TBD markers found")

    covered = set(feature["covered_requirements"])
    inactive_requirements = parse_traceability_inactive_requirements(traceability_text)
    requirement_set = set(requirements) - inactive_requirements
    unmapped_requirements = sorted(requirement_set - covered)
    c4_failures = []
    if not artifacts.traceability:
        c4_failures.append("missing traceability artifact")
    if not artifacts.feature:
        c4_failures.append("missing feature artifact")
    if unmapped_requirements:
        c4_failures.append("requirements without scenario tags")
    if feature["untagged_scenarios"]:
        c4_failures.append("scenarios without REQ/NFR tags")

    c5_failures = []
    if not artifacts.risks:
        c5_failures.append("missing risk artifact")
    if risks["unresolved_high_risks"] > thresholds["max_high_risks"]:
        c5_failures.append("unresolved high risks exceed threshold")
    if open_questions > thresholds["max_open_questions"]:
        c5_failures.append("open questions remain")

    return {
        "artifacts": {
            "node_dir": str(artifacts.node_dir),
            "prd": str(artifacts.prd) if artifacts.prd else None,
            "feature": str(artifacts.feature) if artifacts.feature else None,
            "architecture": str(artifacts.architecture) if artifacts.architecture else None,
            "architecture_files": [str(path) for path in artifacts.architecture_files],
            "architecture_validation": str(artifacts.architecture_validation) if artifacts.architecture_validation else None,
            "traceability": str(artifacts.traceability) if artifacts.traceability else None,
            "risks": str(artifacts.risks) if artifacts.risks else None,
            "missing": missing_artifacts,
        },
        "requirements": {
            "count": len(requirements),
            "ids": requirements,
        },
        "C1_behavior_complexity": status(
            "fail" if c1_failures else "pass",
            "; ".join(c1_failures) if c1_failures else "Static behavior thresholds passed.",
            feature,
        ),
        "C2_contract_boundary": status(
            "fail" if c2_failures else "pass",
            "; ".join(c2_failures) if c2_failures else "Contract fields are present.",
            {"fields": fields, "missing_fields": missing_fields},
        ),
        "C3_ai_context_control": status(
            "fail" if c3_failures else "pass",
            "; ".join(c3_failures) if c3_failures else "Static context thresholds passed.",
            {
                "estimated_tokens": token_estimate,
                "open_questions": open_questions,
                "todo_markers": todos,
            },
        ),
        "C4_verifiability": status(
            "fail" if c4_failures else "pass",
            "; ".join(c4_failures) if c4_failures else "Static traceability checks passed.",
            {
                "unmapped_requirements": unmapped_requirements,
                "deferred_or_excluded_requirements": sorted(inactive_requirements),
                "untagged_scenarios": feature["untagged_scenarios"],
                "covered_requirements": feature["covered_requirements"],
            },
        ),
        "C5_risk_decomposition": status(
            "fail" if c5_failures else "pass",
            "; ".join(c5_failures) if c5_failures else "Static risk thresholds passed.",
            risks | {"open_questions": open_questions},
        ),
    }


def load_thresholds(node_dir: Path) -> Dict[str, Any]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    for name in ("leaf-gate.config.json", "leaf_gate.config.json"):
        path = node_dir / name
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            thresholds.update(data.get("thresholds", data))
    return thresholds


def static_decision(report: Dict[str, Any]) -> Tuple[str, str]:
    missing = report["artifacts"]["missing"]
    if missing:
        return "NEEDS_SPEC_REFINEMENT", f"Missing required artifacts: {', '.join(missing)}."
    failed = [criterion for criterion in CRITERIA if report[criterion]["status"] == "fail"]
    if failed:
        return "NEEDS_DECOMPOSITION", f"Static checks failed: {', '.join(failed)}."
    return "STATIC_PASS_REQUIRES_LLM", "Static checks passed. Run LLM semantic judgement before LEAF_READY."


def combine_with_llm(static_report: Dict[str, Any], llm_path: Path, thresholds: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    try:
        llm_report = json.loads(llm_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "NEEDS_SPEC_REFINEMENT", f"LLM judgement is not valid JSON: {exc}.", {}

    judgement = llm_report.get("llm_judgement", {})
    missing = [criterion for criterion in CRITERIA if criterion not in judgement]
    if missing:
        return "NEEDS_SPEC_REFINEMENT", f"LLM judgement missing criteria: {', '.join(missing)}.", llm_report

    low_confidence = []
    failed = []
    warned = []
    for criterion in CRITERIA:
        item = judgement[criterion]
        item_status = str(item.get("status", "")).lower()
        confidence = float(item.get("confidence", 0))
        evidence = item.get("evidence") or []
        if not evidence:
            failed.append(f"{criterion}: missing evidence")
        if item_status == "fail":
            failed.append(criterion)
        elif item_status == "warn":
            warned.append(criterion)
        elif item_status != "pass":
            failed.append(f"{criterion}: invalid status")
        if confidence < thresholds["min_llm_confidence"]:
            low_confidence.append(criterion)

    static_failed = [criterion for criterion in CRITERIA if static_report[criterion]["status"] == "fail"]
    high_risks = static_report["C5_risk_decomposition"]["evidence"].get("unresolved_high_risks", 0)

    if static_report["artifacts"]["missing"]:
        return "NEEDS_SPEC_REFINEMENT", "Required artifacts are missing.", llm_report
    if static_failed:
        return "NEEDS_DECOMPOSITION", f"Static checks failed: {', '.join(static_failed)}.", llm_report
    if failed:
        return "NEEDS_DECOMPOSITION", f"LLM judgement failed: {', '.join(failed)}.", llm_report
    if high_risks:
        return "HUMAN_REVIEW", "Unresolved high risks remain.", llm_report
    if low_confidence or warned:
        parts = []
        if low_confidence:
            parts.append(f"low confidence: {', '.join(low_confidence)}")
        if warned:
            parts.append(f"warnings: {', '.join(warned)}")
        return "HUMAN_REVIEW", "; ".join(parts), llm_report
    return "LEAF_READY", "Static checks and LLM judgement passed.", llm_report


def build_report(node_dir: Path, llm_path: Optional[Path], prepare: bool = True) -> Dict[str, Any]:
    thresholds = load_thresholds(node_dir)
    artifacts = find_artifacts(node_dir)
    if prepare:
        artifacts = prepare_evidence(artifacts)
    checks = static_checks(artifacts, thresholds)
    decision, reason = static_decision(checks)
    llm_report: Dict[str, Any] = {}
    if llm_path:
        decision, reason, llm_report = combine_with_llm(checks, llm_path, thresholds)
    return {
        "node_id": node_dir.name,
        "decision": decision,
        "summary": reason,
        "thresholds": thresholds,
        "static_checks": checks,
        "llm_judgement": llm_report.get("llm_judgement"),
        "next_action": next_action(decision),
    }


def next_action(decision: str) -> Dict[str, Any]:
    if decision == "LEAF_READY":
        return {"type": "vibecode", "children": [], "notes": ["Proceed to implementation package."]}
    if decision == "NEEDS_DECOMPOSITION":
        return {"type": "decompose", "children": [], "notes": ["Generate lower-layer PRDs for failed criteria."]}
    if decision == "HUMAN_REVIEW":
        return {"type": "human_review", "children": [], "notes": ["Resolve risk or low-confidence judgement."]}
    return {"type": "refine_spec", "children": [], "notes": ["Add or clarify required artifacts."]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Leaf Gate static checks for a PRD node.")
    parser.add_argument("node_dir", type=Path, help="Directory containing PRD node artifacts.")
    parser.add_argument("--output", type=Path, help="Where to write report JSON. Defaults to stdout.")
    parser.add_argument("--llm-judgement", type=Path, help="Optional LLM judgement JSON to combine with static checks.")
    parser.add_argument("--skip-prepare", action="store_true", help="Skip generated traceability.md and risks.md refresh.")
    args = parser.parse_args()

    if not args.node_dir.exists() or not args.node_dir.is_dir():
        raise SystemExit(f"Node directory does not exist: {args.node_dir}")

    report = build_report(args.node_dir, args.llm_judgement, prepare=not args.skip_prepare)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
