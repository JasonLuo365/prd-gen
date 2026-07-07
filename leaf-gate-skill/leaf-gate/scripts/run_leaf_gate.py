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
    "leaf_score_pass": 10,
    "leaf_score_warn": 20,
    "max_scenario_points": 10,
    "max_expanded_cases": 20,
    "max_steps_per_scenario": 12,
    "max_req_tags_per_scenario": 3,
    "max_open_questions": 0,
    "max_high_risks": 0,
    "max_estimated_tokens": 24000,
    "max_implementation_pack_tokens": 18000,
    "max_full_artifact_tokens": 50000,
    "min_llm_confidence": 0.75,
}

CRITERIA = [
    "C1_behavior_complexity",
    "C2_contract_boundary",
    "C3_ai_context_control",
    "C4_verifiability",
    "C5_risk_decomposition",
]

CURRENT_REQ_ID_RE = r"(?:REQ|NFR|UC|QAS)-(?:[A-Z]+)?\d{3,}"
TRACE_TAG_ID_RE = r"(?:REQ|NFR|UC|QAS|MET)-(?:[A-Z]+)?\d{3,}"


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
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceRef:
    artifact: str
    line: Optional[int] = None
    label: str = ""

    def to_report(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"artifact": self.artifact}
        if self.line is not None:
            payload["line"] = self.line
        if self.label:
            payload["label"] = self.label
        return payload


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    priority: str = "unknown"
    status: str = "active"
    parent_id: Optional[str] = None
    section: str = ""
    source: EvidenceRef = field(default_factory=lambda: EvidenceRef("prd"))

    def to_report(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "section": self.section,
            "priority": self.priority,
            "status": self.status,
            "source": self.source.to_report(),
        }
        if self.parent_id:
            payload["parent_req"] = self.parent_id
        return payload


@dataclass(frozen=True)
class Step:
    keyword: str
    text: str
    source: EvidenceRef

    def to_report(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "text": self.text,
            "source": self.source.to_report(),
        }


@dataclass(frozen=True)
class Scenario:
    id: Optional[str]
    name: str
    tags: List[str]
    requirement_ids: List[str]
    metric_ids: List[str]
    steps: List[Step]
    outline: bool = False
    example_rows: int = 0
    assertion_quality: str = "none"
    source: EvidenceRef = field(default_factory=lambda: EvidenceRef("feature"))

    @property
    def composite(self) -> bool:
        return len(self.requirement_ids) > 2 or any(tag.startswith("COMP-") for tag in self.tags)

    def to_report(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "outline": self.outline,
            "tags": [f"@{tag}" for tag in self.tags],
            "req_tags": self.requirement_ids,
            "trace_tags": sorted(set(self.requirement_ids + self.metric_ids)),
            "metric_tags": self.metric_ids,
            "composite": self.composite,
            "assertion_quality": self.assertion_quality,
            "step_count": len(self.steps),
            "example_rows": self.example_rows,
            "source": self.source.to_report(),
        }


@dataclass(frozen=True)
class Contract:
    id: str
    provider: str = ""
    consumer: str = ""
    trigger: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    observability: List[str] = field(default_factory=list)
    source: EvidenceRef = field(default_factory=lambda: EvidenceRef("architecture"))

    def to_report(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "consumer": self.consumer,
            "trigger": self.trigger,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "errors": self.errors,
            "states": self.states,
            "side_effects": self.side_effects,
            "dependencies": self.dependencies,
            "observability": self.observability,
            "source": self.source.to_report(),
        }


@dataclass(frozen=True)
class Risk:
    id: str
    class_: str
    severity: str = "medium"
    status: str = "open"
    source: EvidenceRef = field(default_factory=lambda: EvidenceRef("risks"))

    def to_report(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "class": self.class_,
            "severity": self.severity,
            "status": self.status,
            "source": self.source.to_report(),
        }


@dataclass(frozen=True)
class ProjectProfile:
    trace_terms: List[str] = field(default_factory=list)
    trace_synonyms: Dict[str, List[str]] = field(default_factory=dict)
    architecture_markers: List[str] = field(default_factory=list)
    risk_class_patterns: Dict[str, List[str]] = field(default_factory=dict)
    high_risk_classes: List[str] = field(default_factory=list)
    active_requirement_statuses: List[str] = field(default_factory=lambda: ["active"])

    def merge(self, data: Dict[str, Any]) -> "ProjectProfile":
        return ProjectProfile(
            trace_terms=list(data.get("trace_terms", self.trace_terms)),
            trace_synonyms={key: list(value) for key, value in data.get("trace_synonyms", self.trace_synonyms).items()},
            architecture_markers=list(data.get("architecture_markers", self.architecture_markers)),
            risk_class_patterns={key: list(value) for key, value in data.get("risk_class_patterns", self.risk_class_patterns).items()},
            high_risk_classes=list(data.get("high_risk_classes", self.high_risk_classes)),
            active_requirement_statuses=list(data.get("active_requirement_statuses", self.active_requirement_statuses)),
        )

    def to_report(self) -> Dict[str, Any]:
        return {
            "trace_terms": self.trace_terms,
            "trace_synonyms": self.trace_synonyms,
            "architecture_markers": self.architecture_markers,
            "risk_class_patterns": self.risk_class_patterns,
            "high_risk_classes": self.high_risk_classes,
            "active_requirement_statuses": self.active_requirement_statuses,
        }


@dataclass(frozen=True)
class LeafGateConfig:
    thresholds: Dict[str, Any]
    profile: ProjectProfile
    config_path: Optional[Path] = None
    profile_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)


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
        matches = sorted(path for path in node_dir.glob(pattern) if not path.name.startswith("leaf-gate."))
        if matches:
            return matches[0]
    return None


def resolve_path(node_dir: Path, path: Optional[Path]) -> Optional[Path]:
    if path is None:
        return None
    return path if path.is_absolute() else node_dir / path


def existing_file(node_dir: Path, path: Optional[Path]) -> Optional[Path]:
    candidate = resolve_path(node_dir, path)
    return candidate if candidate and candidate.exists() and candidate.is_file() else None


def markdown_files(path: Path) -> List[Path]:
    return sorted(file for file in path.glob("*.md") if file.is_file())


def architecture_dir_artifacts(path: Path) -> Tuple[Path, List[Path], Optional[Path]]:
    output_dir = path / "output"
    source_dir = output_dir if output_dir.exists() and output_dir.is_dir() else path
    files = markdown_files(source_dir)
    validation = path / "validation-report.md"
    if validation.exists() and validation.is_file() and validation not in files:
        files.append(validation)
    return source_dir, files, validation if validation.exists() else None


def find_architecture_artifacts(
    node_dir: Path, architecture_path: Optional[Path] = None
) -> Tuple[Optional[Path], List[Path], Optional[Path]]:
    explicit = resolve_path(node_dir, architecture_path)
    if explicit:
        if explicit.is_file():
            return explicit, [explicit], None
        if explicit.is_dir():
            source_dir, files, validation = architecture_dir_artifacts(explicit)
            return source_dir, files, validation
        return None, [], None

    architecture_file = find_first(
        node_dir,
        ["architecture.yaml", "architecture.yml", "architecture.json", "architecture.md"],
        ["*architecture*.yaml", "*architecture*.yml", "*architecture*.json", "*architecture*.md", "*arch*.md"],
    )
    if architecture_file:
        return architecture_file, [architecture_file], None

    for name in ("architecture", "output"):
        architecture_dir = node_dir / name
        if architecture_dir.exists() and architecture_dir.is_dir():
            source_dir, files, validation = architecture_dir_artifacts(architecture_dir)
            if files:
                return source_dir, files, validation
    return None, [], None


def find_artifacts(
    node_dir: Path,
    prd_path: Optional[Path] = None,
    feature_path: Optional[Path] = None,
    architecture_path: Optional[Path] = None,
    traceability_path: Optional[Path] = None,
    risks_path: Optional[Path] = None,
) -> ArtifactSet:
    warnings: List[str] = []
    architecture, architecture_files, architecture_validation = find_architecture_artifacts(node_dir, architecture_path)
    prd = existing_file(node_dir, prd_path) if prd_path else find_first(node_dir, ["prd.md", "PRD.md"], ["*prd*.md", "*PRD*.md"])
    feature = existing_file(node_dir, feature_path) if feature_path else find_first(node_dir, ["testcase.feature"], ["*.feature"])
    traceability = (
        existing_file(node_dir, traceability_path)
        if traceability_path
        else find_first(
            node_dir,
            ["traceability.md", "traceability.yaml", "traceability.yml", "traceability.json"],
            ["*traceability*.md", "*traceability*.yaml", "*traceability*.yml", "*traceability*.json", "*mapping*.md"],
        )
    )
    risks = (
        existing_file(node_dir, risks_path)
        if risks_path
        else find_first(
            node_dir,
            ["risks.md", "risk_register.md", "risks.yaml", "risks.yml", "risks.json"],
            ["*risk*.md", "*risk*.yaml", "*risk*.yml", "*risk*.json"],
        )
    )
    for label, requested, found in (
        ("prd", prd_path, prd),
        ("feature", feature_path, feature),
        ("architecture", architecture_path, architecture),
        ("traceability", traceability_path, traceability),
        ("risks", risks_path, risks),
    ):
        if requested and not found:
            warnings.append(f"Explicit {label} path was not found: {requested}")
    return ArtifactSet(
        node_dir=node_dir,
        prd=prd,
        feature=feature,
        architecture=architecture,
        traceability=traceability,
        risks=risks,
        architecture_files=architecture_files,
        architecture_validation=architecture_validation,
        warnings=warnings,
    )


def status(level: str, reason: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": level,
        "reason": reason,
        "evidence": evidence or {},
    }


def count_requirements(prd_text: str) -> List[str]:
    return [requirement["id"] for requirement in extract_requirements(prd_text)]


def requirement_state(section: str, line: str) -> Tuple[str, str]:
    text = f"{section} {line}".lower()
    if re.search(r"won'?t|wont|non[- ]?goals?|out of scope|不涉及|排除|excluded?", text):
        return "wont", "excluded"
    if re.search(r"could have|deferred|延期|未进入|not applicable|not_applicable", text):
        return "could", "deferred"
    if "should have" in text:
        return "should", "active"
    if "must have" in text:
        return "must", "active"
    return "unknown", "active"


def add_requirement(
    requirements: Dict[str, Requirement],
    req_id: str,
    text: str,
    section: str,
    line: str,
    next_line: str = "",
    line_number: Optional[int] = None,
    source_artifact: str = "prd",
) -> None:
    priority, item_status = requirement_state(section, line)
    parent_id = None
    parent_match = re.search(rf"parent_req:\s*({CURRENT_REQ_ID_RE})\b", next_line)
    if parent_match:
        parent_id = parent_match.group(1)
    item = Requirement(
        id=req_id,
        text=text.strip() or line.strip(),
        section=section,
        priority=priority,
        status=item_status,
        parent_id=parent_id,
        source=EvidenceRef(source_artifact, line_number),
    )
    requirements.setdefault(req_id, item)


def parse_requirements(prd_text: str, source_artifact: str = "prd") -> List[Requirement]:
    requirements: Dict[str, Requirement] = {}
    section = ""
    lines = prd_text.splitlines()
    for index, line in enumerate(lines):
        line_number = index + 1
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1)
            heading_req = re.match(rf"^\s*({CURRENT_REQ_ID_RE})\s*[-:：]\s*(.+?)\s*$", section)
            if heading_req:
                add_requirement(
                    requirements,
                    heading_req.group(1),
                    heading_req.group(2),
                    section,
                    line,
                    line_number=line_number,
                    source_artifact=source_artifact,
                )
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        bullet_match = re.match(rf"^\s*[-*]\s+\[({CURRENT_REQ_ID_RE})\]\s*(.+?)\s*$", line)
        colon_match = re.match(rf"^\s*[-*]?\s*({CURRENT_REQ_ID_RE})\s*[:：-]\s*(.+?)\s*$", line)
        table_match = re.match(rf"^\s*\|\s*({CURRENT_REQ_ID_RE})\s*\|\s*(.+?)\s*\|", line)
        req_match = bullet_match or colon_match or table_match
        if req_match:
            add_requirement(
                requirements,
                req_match.group(1),
                req_match.group(2),
                section,
                line,
                next_line,
                line_number=line_number,
                source_artifact=source_artifact,
            )
    return [requirements[req_id] for req_id in sorted(requirements)]


def extract_requirements(prd_text: str) -> List[Dict[str, Any]]:
    return [requirement.to_report() for requirement in parse_requirements(prd_text)]


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


def assertion_quality(block: str) -> str:
    then_lines = re.findall(r"(?im)^\s*(?:Then|And)\s+(.+?)\s*$", block)
    if not then_lines:
        return "none"
    combined = " ".join(then_lines)
    if re.search(r"\b(reasonably|properly|correctly|safely|works?|handled?)\b|合理|正确处理|安全处理", combined, re.IGNORECASE):
        return "weak"
    if re.search(r"\d|<=|>=|=|P95|错误|error|状态|state|事件|event|返回|response|写入|删除|不可读取|拒绝|允许", combined, re.IGNORECASE):
        return "strong"
    return "medium"


def assertion_quality_from_steps(steps: List[Step]) -> str:
    then_text = " ".join(step.text for step in steps if step.keyword.lower() in {"then", "and"})
    if not then_text:
        return "none"
    return assertion_quality("\n".join(f"Then {step.text}" for step in steps if step.keyword.lower() in {"then", "and"}))


def _scenario_from_parts(
    name: str,
    tags: List[str],
    steps: List[Step],
    outline: bool,
    example_rows: int,
    line_number: Optional[int],
    source_artifact: str,
) -> Scenario:
    clean_tags = sorted({tag[1:] if tag.startswith("@") else tag for tag in tags})
    req_tags = sorted(tag for tag in clean_tags if re.match(rf"^{CURRENT_REQ_ID_RE}$", tag))
    metric_tags = sorted(tag for tag in clean_tags if re.match(r"^MET-(?:[A-Z]+)?\d{3,}$", tag))
    scenario_id = next((tag for tag in clean_tags if re.match(r"^(?:SCN|SCE)-[A-Z]*\d{3,}$", tag)), None)
    return Scenario(
        id=scenario_id,
        name=name,
        tags=clean_tags,
        requirement_ids=req_tags,
        metric_ids=metric_tags,
        steps=steps,
        outline=outline,
        example_rows=example_rows,
        assertion_quality=assertion_quality_from_steps(steps),
        source=EvidenceRef(source_artifact, line_number),
    )


def parse_feature_official(feature_text: str, source_artifact: str = "feature") -> Optional[List[Scenario]]:
    try:
        from gherkin.parser import Parser  # type: ignore
    except Exception:
        return None
    try:
        document = Parser().parse(feature_text)
    except Exception:
        return None

    scenarios: List[Scenario] = []
    feature = document.get("feature") or {}
    for child in feature.get("children") or []:
        scenario_data = child.get("scenario")
        if not scenario_data:
            continue
        tags = [tag.get("name", "") for tag in scenario_data.get("tags") or [] if tag.get("name")]
        steps = [
            Step(
                keyword=(step.get("keyword") or "").strip(),
                text=step.get("text") or "",
                source=EvidenceRef(source_artifact, step.get("location", {}).get("line")),
            )
            for step in scenario_data.get("steps") or []
        ]
        examples = scenario_data.get("examples") or []
        example_rows = sum(len(example.get("tableBody") or []) for example in examples)
        keyword = str(scenario_data.get("keyword") or "")
        scenarios.append(
            _scenario_from_parts(
                name=scenario_data.get("name") or "",
                tags=tags,
                steps=steps,
                outline="outline" in keyword.lower() or bool(examples),
                example_rows=example_rows,
                line_number=scenario_data.get("location", {}).get("line"),
                source_artifact=source_artifact,
            )
        )
    return scenarios


def parse_feature_fallback(feature_text: str, source_artifact: str = "feature") -> List[Scenario]:
    scenarios: List[Scenario] = []
    pending_tags: List[str] = []
    current_name: Optional[str] = None
    current_tags: List[str] = []
    current_steps: List[Step] = []
    current_outline = False
    current_line: Optional[int] = None
    in_examples = False
    example_rows = 0

    def flush() -> None:
        nonlocal current_name, current_tags, current_steps, current_outline, current_line, in_examples, example_rows
        if current_name is None:
            return
        scenarios.append(
            _scenario_from_parts(
                current_name,
                current_tags,
                current_steps,
                current_outline,
                example_rows,
                current_line,
                source_artifact,
            )
        )
        current_name = None
        current_tags = []
        current_steps = []
        current_outline = False
        current_line = None
        in_examples = False
        example_rows = 0

    for line_number, raw_line in enumerate(feature_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            pending_tags = re.findall(r"@\S+", line)
            continue
        scenario_match = re.match(r"^(Scenario(?:\s+Outline)?|Example):\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if scenario_match:
            flush()
            current_name = scenario_match.group(2)
            current_tags = pending_tags
            pending_tags = []
            current_outline = "outline" in scenario_match.group(1).lower()
            current_line = line_number
            continue
        if current_name is None:
            pending_tags = []
            continue
        if re.match(r"^Examples?:\s*$", line, flags=re.IGNORECASE):
            in_examples = True
            continue
        if in_examples and re.match(r"^\|.+\|$", line):
            example_rows += 1
            continue
        step_match = re.match(r"^(Given|When|Then|And|But|\*)\s+(.+?)\s*$", line, flags=re.IGNORECASE)
        if step_match:
            current_steps.append(
                Step(
                    keyword=step_match.group(1),
                    text=step_match.group(2),
                    source=EvidenceRef(source_artifact, line_number),
                )
            )
    flush()
    for scenario in scenarios:
        if scenario.outline and scenario.example_rows > 0:
            object.__setattr__(scenario, "example_rows", max(0, scenario.example_rows - 1))
    return scenarios


def feature_report(scenarios: List[Scenario], parser_name: str) -> Dict[str, Any]:
    scenario_items = [scenario.to_report() for scenario in scenarios]
    scenario_count = len(scenario_items)
    outline_count = sum(1 for item in scenario_items if item["outline"])
    expanded_case_count = sum(max(1, item["example_rows"]) for item in scenario_items)
    max_steps = max((item["step_count"] for item in scenario_items), default=0)
    max_req_tags = max((len(item["req_tags"]) for item in scenario_items), default=0)
    untagged = [item["name"] for item in scenario_items if not item["trace_tags"]]
    covered_reqs = sorted({tag for item in scenario_items for tag in item["req_tags"]})
    composite_count = sum(1 for item in scenario_items if item["composite"])
    metric_only_count = sum(1 for item in scenario_items if item["metric_tags"] and not item["req_tags"])
    weak_assertions = [
        item["name"]
        for item in scenario_items
        if item["assertion_quality"] in {"weak", "none"}
    ]
    scenario_points = (
        expanded_case_count
        + composite_count * 2
        + max(0, max_steps - 5)
        + max(0, max_req_tags - 2) * 2
        + metric_only_count
    )

    return {
        "parser": parser_name,
        "scenario_count": scenario_count,
        "scenario_outline_count": outline_count,
        "expanded_case_count": expanded_case_count,
        "max_steps_per_scenario": max_steps,
        "max_req_tags_per_scenario": max_req_tags,
        "composite_scenario_count": composite_count,
        "metric_only_scenario_count": metric_only_count,
        "weak_assertion_scenarios": weak_assertions,
        "scenario_points": scenario_points,
        "untagged_scenarios": untagged,
        "covered_requirements": covered_reqs,
        "scenarios": scenario_items,
    }


def parse_scenarios(feature_text: str, source_artifact: str = "feature") -> Tuple[List[Scenario], str]:
    official = parse_feature_official(feature_text, source_artifact)
    if official is not None:
        return official, "gherkin-official"
    return parse_feature_fallback(feature_text, source_artifact), "fallback"


def parse_feature(feature_text: str) -> Dict[str, Any]:
    scenarios, parser_name = parse_scenarios(feature_text)
    return feature_report(scenarios, parser_name)


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
            deferred.update(re.findall(rf"\b{CURRENT_REQ_ID_RE}\b", line))

    in_could_have = False
    for line in prd_text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            in_could_have = "could have" in title
            continue
        if in_could_have:
            deferred.update(re.findall(rf"\b{CURRENT_REQ_ID_RE}\b", line))
    return deferred


def relative_to_node(path: Path, node_dir: Path) -> str:
    try:
        return str(path.relative_to(node_dir)).replace("\\", "/")
    except ValueError:
        return str(path)


DEFAULT_TRACE_TERMS: List[str] = []
DEFAULT_TRACE_SYNONYMS: Dict[str, List[str]] = {}

ARCHITECTURE_MARKERS = [
    r"\bmodule\b",
    r"\bbc\b",
    r"\bapi\b",
    r"\bpost\b",
    r"/api/",
    r"\bevent\b",
    r"\bworker\b",
    "模块",
    "接口",
    "契约",
    "输入",
    "输出",
    "错误码",
    "状态",
    "事件",
    "聚合",
    "部署",
    "QAS",
    "UC-",
    "ASR",
    "Redis",
    "PostgreSQL",
    "Object Storage",
]


def normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def extract_boundary_terms(text: str) -> List[str]:
    terms: set[str] = set()
    range_pattern = re.compile(r"(\d+)\s*(?:到|至|-|~|–)\s*(\d+)\s*(张|MB|秒|分钟|天|轮|次|位)?", re.IGNORECASE)
    for start, end, unit in range_pattern.findall(text):
        unit = unit or ""
        terms.update({f"{start}到{end}{unit}", f"{start}-{end}", f"{start}–{end}"})
        if unit:
            terms.update({f"{start}{unit}", f"{end}{unit}"})
    single_pattern = re.compile(r"(?:<=|>=|<|>|=)?\s*(\d+)\s*(张|MB|秒|分钟|天|轮|次|位)", re.IGNORECASE)
    for value, unit in single_pattern.findall(text):
        terms.add(f"{value}{unit}")
    if "P95" in text or "p95" in text.lower():
        terms.add("P95")
    return sorted(terms)


def extract_generic_trace_terms(text: str) -> List[str]:
    stopwords = {
        "and",
        "are",
        "can",
        "for",
        "from",
        "have",
        "must",
        "shall",
        "should",
        "system",
        "then",
        "user",
        "when",
        "with",
    }
    terms = set(re.findall(r"/[A-Za-z0-9_./{}-]+|\b[A-Za-z][A-Za-z0-9_/-]{3,}\b", text))
    return sorted({term for term in terms if term.lower() not in stopwords}, key=lambda item: (len(item), item), reverse=True)


def extract_trace_terms(text: str, profile: Optional[ProjectProfile] = None) -> List[str]:
    profile = profile or ProjectProfile()
    normalized = normalize_for_match(text)
    terms = []
    for term in [*DEFAULT_TRACE_TERMS, *profile.trace_terms]:
        if normalize_for_match(term) in normalized:
            terms.append(term)
    terms.extend(extract_generic_trace_terms(text))
    terms.extend(extract_boundary_terms(text))
    return sorted(set(terms), key=lambda item: (len(item), item), reverse=True)


def term_variants(term: str, profile: Optional[ProjectProfile] = None) -> List[str]:
    profile = profile or ProjectProfile()
    variants = [term]
    variants.extend(DEFAULT_TRACE_SYNONYMS.get(term, []))
    variants.extend(profile.trace_synonyms.get(term, []))
    if term.upper() in {"P95"}:
        variants.extend([term.lower(), term.upper()])
    return variants


def has_match(term: str, architecture_text: str, profile: Optional[ProjectProfile] = None) -> bool:
    normalized_arch = normalize_for_match(architecture_text)
    return any(normalize_for_match(variant) in normalized_arch for variant in term_variants(term, profile))


def has_architecture_marker(text: str, profile: Optional[ProjectProfile] = None) -> bool:
    profile = profile or ProjectProfile()
    markers = [*ARCHITECTURE_MARKERS, *profile.architecture_markers]
    return any(re.search(marker, text, flags=re.IGNORECASE) for marker in markers)


def architecture_evidence(
    req_id: str,
    requirement_text: str,
    scenario_names: List[str],
    architecture_files: Iterable[Path],
    node_dir: Path,
    profile: Optional[ProjectProfile] = None,
) -> Dict[str, Any]:
    profile = profile or ProjectProfile()
    references = []
    best_strength = "none"
    best_rank = 0
    all_matched_terms: set[str] = set()
    context_text = " ".join([requirement_text, *scenario_names])
    trace_terms = extract_trace_terms(context_text, profile)
    boundary_terms = set(extract_boundary_terms(context_text))
    ranks = {"none": 0, "weak": 1, "medium": 2, "strong": 3}
    for path in architecture_files:
        text = read_text(path)
        matched_terms = [term for term in trace_terms if has_match(term, text, profile)]
        boundary_hits = [term for term in matched_terms if term in boundary_terms]
        marker = has_architecture_marker(text, profile)
        if req_id in text:
            strength = "strong"
        elif marker and boundary_hits and len(matched_terms) >= 2:
            strength = "strong"
        elif marker and len(matched_terms) >= 2:
            strength = "medium"
        elif boundary_hits and len(matched_terms) >= 2:
            strength = "medium"
        elif matched_terms:
            strength = "weak"
        else:
            strength = "none"

        if ranks[strength] > 0:
            shown_terms = ", ".join(matched_terms[:6])
            references.append(f"{relative_to_node(path, node_dir)} ({strength}: {shown_terms})")
            all_matched_terms.update(matched_terms)
        if ranks[strength] > best_rank:
            best_strength = strength
            best_rank = ranks[strength]

    return {
        "references": references,
        "strength": best_strength,
        "matched_terms": sorted(all_matched_terms),
    }


def build_traceability_text(artifacts: ArtifactSet, profile: Optional[ProjectProfile] = None) -> str:
    profile = profile or ProjectProfile()
    prd_text = read_text(artifacts.prd)
    feature_text = read_text(artifacts.feature)
    feature = parse_feature(feature_text)
    scenarios_by_req = scenario_map(feature)
    deferred = detect_deferred_requirements(prd_text, feature_text)
    rows = []
    for requirement in extract_requirements(prd_text):
        req_id = requirement["id"]
        requirement_text = requirement["text"]
        if requirement.get("parent_req"):
            requirement_text = f"{requirement_text}<br>parent_req: {requirement['parent_req']}"
        scenarios = scenarios_by_req.get(req_id, [])
        evidence = architecture_evidence(
            req_id,
            requirement["text"],
            scenarios,
            artifacts.architecture_files,
            artifacts.node_dir,
            profile,
        )
        evidence_references = evidence["references"]
        evidence_strength = evidence["strength"]
        if scenarios and evidence_strength in {"strong", "medium"}:
            status_value = "covered"
        elif req_id in deferred:
            status_value = "deferred"
        elif not scenarios:
            status_value = "missing_testcase"
        elif evidence_strength == "weak":
            status_value = "weak_evidence"
        elif not evidence_references:
            status_value = "missing_architecture"
        else:
            status_value = "missing_architecture"
        rows.append(
            "| {req_id} | {text} | {scenarios} | {evidence} | {strength} | {status} |".format(
                req_id=req_id,
                text=requirement_text.replace("|", "\\|"),
                scenarios=", ".join(scenarios) if scenarios else "none",
                evidence=", ".join(evidence_references).replace("|", "\\|") if evidence_references else "none",
                strength=evidence_strength,
                status=status_value,
            )
        )

    return "\n".join(
        [
            "# Traceability",
            "",
            "> Generated by Leaf Gate prepare evidence from the current node PRD, testcase, and architecture package.",
            "",
            "| Requirement | Requirement text | Testcase scenarios | Architecture evidence | Evidence strength | Status |",
            "| --- | --- | --- | --- | --- | --- |",
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
        inactive.update(re.findall(rf"\b{CURRENT_REQ_ID_RE}\b", line))
    return inactive


def parse_traceability_coverage_gaps(traceability_text: str) -> List[str]:
    gaps = []
    failing_statuses = {"missing_testcase", "missing_architecture", "weak_evidence"}
    for line in traceability_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0] in {"Requirement", "---"}:
            continue
        req_id = cells[0]
        status_value = cells[-1]
        if status_value in failing_statuses:
            gaps.append(f"{req_id}: {status_value}")
    return gaps


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


def build_risks_text(artifacts: ArtifactSet, profile: Optional[ProjectProfile] = None) -> str:
    traceability_text = build_traceability_text(artifacts, profile)
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
        if not line.lstrip().startswith("|") or not re.search(r"missing_|weak_evidence", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        status_value = cells[-1]
        if status_value not in {"missing_testcase", "missing_architecture", "weak_evidence"}:
            continue
        rows.append(
            "| Coverage gap for {req_id} | Automatic verification may be incomplete ({status}) | high | open | Add strong or medium architecture/testcase evidence before Leaf Gate can pass | traceability.md |".format(
                req_id=cells[0],
                status=status_value,
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


def prepare_evidence(artifacts: ArtifactSet, profile: Optional[ProjectProfile] = None) -> ArtifactSet:
    if artifacts.prd and artifacts.feature:
        traceability_path = artifacts.node_dir / "traceability.md"
        risks_path = artifacts.node_dir / "risks.md"
        traceability_path.write_text(build_traceability_text(artifacts, profile), encoding="utf-8")
        risks_path.write_text(build_risks_text(artifacts, profile), encoding="utf-8")
        artifacts.traceability = traceability_path
        artifacts.risks = risks_path
    return artifacts


def contract_fields(architecture_text: str) -> Dict[str, bool]:
    aliases = {
        "inputs": [r"\binputs?\b", r"\brequest\b", "输入", "入参", "请求"],
        "outputs": [r"\boutputs?\b", r"\bresponse\b", "输出", "响应", "返回"],
        "errors": [r"\berrors?\b", r"\bfailure\b", "错误", "异常", "错误码", "失败"],
        "states": [r"\bstates?\b", r"\btransition\b", "状态", "状态机", "流转"],
        "side_effects": [r"\bside[_ -]effects?\b", r"\bside effects?\b", r"\beffects?\b", "副作用", "持久化", "写入", "发送", "操作"],
        "dependencies": [r"\bdependencies\b", r"\bdepends on\b", "依赖", "外部系统", "调用"],
    }
    found: Dict[str, bool] = {}
    for field, patterns in aliases.items():
        found[field] = any(re.search(pattern, architecture_text, flags=re.IGNORECASE) for pattern in patterns)
    return found


def extract_contracts(architecture_files: Iterable[Path], architecture_text: str, node_dir: Path) -> List[Contract]:
    contracts: List[Contract] = []
    files = list(architecture_files)
    if not files and architecture_text:
        fields = contract_fields(architecture_text)
        if any(fields.values()):
            contracts.append(
                Contract(
                    id="architecture",
                    inputs=["present"] if fields.get("inputs") else [],
                    outputs=["present"] if fields.get("outputs") else [],
                    errors=["present"] if fields.get("errors") else [],
                    states=["present"] if fields.get("states") else [],
                    side_effects=["present"] if fields.get("side_effects") else [],
                    dependencies=["present"] if fields.get("dependencies") else [],
                    source=EvidenceRef("architecture"),
                )
            )
        return contracts

    for path in files:
        text = read_text(path)
        fields = contract_fields(text)
        if not any(fields.values()):
            continue
        contracts.append(
            Contract(
                id=path.stem,
                inputs=["present"] if fields.get("inputs") else [],
                outputs=["present"] if fields.get("outputs") else [],
                errors=["present"] if fields.get("errors") else [],
                states=["present"] if fields.get("states") else [],
                side_effects=["present"] if fields.get("side_effects") else [],
                dependencies=["present"] if fields.get("dependencies") else [],
                source=EvidenceRef(relative_to_node(path, node_dir)),
            )
        )
    return contracts


RISK_CLASS_PATTERNS = {
    "security_auth": [
        r"\blogin\b",
        r"\bauth(?:entication|orization)?\b",
        r"\bsession\b",
        r"\btoken\b",
        "登录",
        "认证",
        "授权",
        "验证码",
        "会话",
    ],
    "privacy_data": [
        r"\bprivacy\b",
        r"\bretention\b",
        r"\bpersonal data\b",
        r"\bmodel training\b",
        "隐私",
        "个人数据",
        "保存",
        "保留",
        "模型训练",
        "数据删除",
    ],
    "destructive_operation": [r"\bdelete\b", r"\bpurge\b", r"\bdestroy\b", "删除", "清除", "不可读取"],
    "financial_legal": [r"\bpayment\b", r"\bbilling\b", r"\blegal\b", r"\bcompliance\b", "支付", "账单", "合规", "审计"],
    "concurrency_time": [r"\bttl\b", r"\bretry\b", r"\block\b", r"\basync\b", "重试", "锁", "异步", "有效期", "超时"],
    "external_dependency": [r"\bgateway\b", r"\bobject storage\b", r"\bllm\b", r"\bapi\b", "网关", "对象存储", "外部", "依赖"],
    "performance_slo": [r"\bp95\b", r"\bslo\b", r"\bsuccess rate\b", "成功率", "响应", "延迟"],
    "ai_nondeterminism": [r"\bllm\b", r"\bprompt\b", r"\bhallucination\b", "提示词", "生成", "幻觉"],
}

HIGH_RISK_CLASSES = {"security_auth", "privacy_data", "destructive_operation", "financial_legal"}


def risk_class_counts(text: str, profile: Optional[ProjectProfile] = None) -> Dict[str, int]:
    profile = profile or ProjectProfile()
    counts: Dict[str, int] = {}
    patterns_by_class = {**RISK_CLASS_PATTERNS, **profile.risk_class_patterns}
    for class_name, patterns in patterns_by_class.items():
        count = sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))
        if count:
            counts[class_name] = count
    return counts


def has_risk_mitigation(text: str) -> bool:
    return bool(
        re.search(
            r"\b(mitigat\w*|retry|audit|metric|test|scenario|rollback|policy|log)\b|缓解|重试|审计|指标|测试|场景|策略|日志|告警",
            text,
            flags=re.IGNORECASE,
        )
    )


def risk_counts(risk_text: str, context_text: str = "", profile: Optional[ProjectProfile] = None) -> Dict[str, Any]:
    profile = profile or ProjectProfile()
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
    combined = "\n".join([risk_text, context_text])
    class_counts = risk_class_counts(combined, profile)
    high_class_names = HIGH_RISK_CLASSES | set(profile.high_risk_classes)
    high_classes = sorted(class_name for class_name in class_counts if class_name in high_class_names)
    unmitigated_high_classes = high_classes if high_classes and not has_risk_mitigation(combined) else []
    risk_items = [
        Risk(
            id=f"RISK-{index:03d}",
            class_=class_name,
            severity="high" if class_name in high_class_names else "medium",
            status="open" if class_name in unmitigated_high_classes else "mitigated",
        ).to_report()
        for index, class_name in enumerate(sorted(class_counts), start=1)
    ]
    return {
        "unresolved_high_risks": high_unresolved + len(unmitigated_high_classes),
        "risk_like_lines": len(re.findall(r"(?im)\b(risk|风险)\b", risk_text)),
        "risk_classes": class_counts,
        "high_risk_classes": high_classes,
        "unmitigated_high_risk_classes": unmitigated_high_classes,
        "items": risk_items,
    }


def estimate_tokens(*texts: str) -> int:
    # Mixed Chinese/English approximation: characters/3 is safer than words/0.75.
    chars = sum(len(text) for text in texts)
    return int(chars / 3) if chars else 0


def implementation_pack_text(
    prd_text: str,
    feature_text: str,
    architecture_files: Iterable[Path],
    traceability_text: str,
    risk_text: str,
) -> str:
    selected = [prd_text, feature_text, traceability_text, risk_text]
    wanted = ("contract", "interface", "接口", "契约", "data-model", "runtime", "validation")
    for path in architecture_files:
        name = path.name.lower()
        if any(term in name for term in wanted):
            selected.append(read_text(path))
    return "\n".join(text for text in selected if text)


def load_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists() or path.suffix.lower() != ".json":
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def find_optional_file(node_dir: Path, requested: Optional[Path], names: Iterable[str]) -> Optional[Path]:
    if requested:
        candidate = resolve_path(node_dir, requested)
        return candidate if candidate and candidate.exists() and candidate.is_file() else None
    for name in names:
        candidate = node_dir / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def read_json_config(path: Optional[Path], label: str, warnings: List[str]) -> Dict[str, Any]:
    if not path:
        return {}
    if path.suffix.lower() != ".json":
        warnings.append(f"{label} must be JSON for the stdlib checker: {path}")
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        warnings.append(f"{label} is not valid JSON: {path}: {exc}")
        return {}


def load_leaf_gate_config(
    node_dir: Path,
    config_path: Optional[Path] = None,
    profile_path: Optional[Path] = None,
) -> LeafGateConfig:
    warnings: List[str] = []
    config_file = find_optional_file(node_dir, config_path, ["leaf-gate.config.json", "leaf_gate.config.json"])
    if config_path and not config_file:
        warnings.append(f"Explicit config path was not found: {config_path}")
    config_data = read_json_config(config_file, "config", warnings)

    thresholds = dict(DEFAULT_THRESHOLDS)
    threshold_data = config_data.get("thresholds")
    if isinstance(threshold_data, dict):
        thresholds.update(threshold_data)
    else:
        thresholds.update({key: value for key, value in config_data.items() if key in DEFAULT_THRESHOLDS})

    configured_profile_path = config_data.get("profile_path")
    if profile_path is None and isinstance(configured_profile_path, str):
        profile_path = Path(configured_profile_path)
    profile_file = find_optional_file(node_dir, profile_path, ["leaf-gate.profile.json", "leaf_gate.profile.json"])
    if profile_path and not profile_file:
        warnings.append(f"Explicit profile path was not found: {profile_path}")

    profile = ProjectProfile()
    profile_data = config_data.get("profile")
    if isinstance(profile_data, dict):
        profile = profile.merge(profile_data)
    profile_file_data = read_json_config(profile_file, "profile", warnings)
    if profile_file_data:
        profile = profile.merge(profile_file_data.get("profile", profile_file_data))

    return LeafGateConfig(
        thresholds=thresholds,
        profile=profile,
        config_path=config_file,
        profile_path=profile_file,
        warnings=warnings,
    )


def static_checks(
    artifacts: ArtifactSet,
    thresholds: Dict[str, Any],
    profile: Optional[ProjectProfile] = None,
) -> Dict[str, Any]:
    profile = profile or ProjectProfile()
    prd_text = read_text(artifacts.prd)
    feature_text = read_text(artifacts.feature)
    architecture_text = read_texts(artifacts.architecture_files) if artifacts.architecture_files else read_text(artifacts.architecture)
    traceability_text = read_text(artifacts.traceability)
    risk_text = read_text(artifacts.risks)

    prd_source = relative_to_node(artifacts.prd, artifacts.node_dir) if artifacts.prd else "prd"
    feature_source = relative_to_node(artifacts.feature, artifacts.node_dir) if artifacts.feature else "feature"
    requirement_models = parse_requirements(prd_text, prd_source)
    requirement_items = [requirement.to_report() for requirement in requirement_models]
    requirements = [requirement.id for requirement in requirement_models]
    scenarios, parser_name = parse_scenarios(feature_text or "", feature_source)
    feature = feature_report(scenarios, parser_name)
    contracts = extract_contracts(artifacts.architecture_files, architecture_text, artifacts.node_dir)
    fields = contract_fields(architecture_text)
    missing_fields = [name for name, present in fields.items() if not present]
    risk_context = "\n".join([prd_text, feature_text, architecture_text, traceability_text])
    risks = risk_counts(risk_text, risk_context, profile)
    full_artifact_tokens = estimate_tokens(prd_text, feature_text, architecture_text, traceability_text, risk_text)
    implementation_pack_tokens = estimate_tokens(
        implementation_pack_text(prd_text, feature_text, artifacts.architecture_files, traceability_text, risk_text)
    )
    token_estimate = implementation_pack_tokens
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
    if feature["scenario_points"] > thresholds["max_scenario_points"]:
        c1_failures.append("scenario points exceed threshold")
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
    if implementation_pack_tokens > thresholds.get("max_implementation_pack_tokens", thresholds["max_estimated_tokens"]):
        c3_failures.append("implementation pack context exceeds threshold")
    if full_artifact_tokens > thresholds.get("max_full_artifact_tokens", 50000):
        c3_failures.append("full artifact context exceeds threshold")
    if open_questions > thresholds["max_open_questions"]:
        c3_failures.append("open questions exceed threshold")
    if todos:
        c3_failures.append("TODO/TBD markers found")

    covered = set(feature["covered_requirements"])
    inactive_requirements = parse_traceability_inactive_requirements(traceability_text)
    inactive_requirements.update(
        requirement.id
        for requirement in requirement_models
        if requirement.status not in profile.active_requirement_statuses
    )
    architecture_evidence_gaps = parse_traceability_coverage_gaps(traceability_text)
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
    if architecture_evidence_gaps:
        c4_failures.append("requirements without usable architecture evidence")

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
            "warnings": artifacts.warnings,
            "inventory": {
                "traceability_source": "provided" if artifacts.traceability else "missing",
                "risks_source": "provided" if artifacts.risks else "missing",
                "architecture_package": str(artifacts.architecture) if artifacts.architecture else None,
            },
        },
        "requirements": {
            "count": len(requirements),
            "ids": requirements,
            "items": requirement_items,
        },
        "C1_behavior_complexity": status(
            "fail" if c1_failures else "pass",
            "; ".join(c1_failures) if c1_failures else "Static behavior thresholds passed.",
            feature,
        ),
        "C2_contract_boundary": status(
            "fail" if c2_failures else "pass",
            "; ".join(c2_failures) if c2_failures else "Contract fields are present.",
            {"fields": fields, "missing_fields": missing_fields, "contracts": [contract.to_report() for contract in contracts]},
        ),
        "C3_ai_context_control": status(
            "fail" if c3_failures else "pass",
            "; ".join(c3_failures) if c3_failures else "Static context thresholds passed.",
            {
                "estimated_tokens": token_estimate,
                "implementation_pack_tokens": implementation_pack_tokens,
                "full_artifact_tokens": full_artifact_tokens,
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
                "architecture_evidence_gaps": architecture_evidence_gaps,
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


def load_thresholds(node_dir: Path, config_path: Optional[Path] = None) -> Dict[str, Any]:
    return load_leaf_gate_config(node_dir, config_path=config_path).thresholds


def static_decision(report: Dict[str, Any]) -> Tuple[str, str]:
    missing = report["artifacts"]["missing"]
    if missing:
        return "NEEDS_REFINEMENT", f"Missing required artifacts: {', '.join(missing)}."
    failed = [criterion for criterion in CRITERIA if report[criterion]["status"] == "fail"]
    if failed:
        c1_reason = report["C1_behavior_complexity"]["reason"]
        broad_scope = "C1_behavior_complexity" in failed and not re.search(
            r"missing testcase|no scenarios", c1_reason, flags=re.IGNORECASE
        )
        risk_classes = report["C5_risk_decomposition"].get("evidence", {}).get("high_risk_classes", [])
        if broad_scope or (risk_classes and "C1_behavior_complexity" in failed):
            return "NEEDS_DECOMPOSITION", f"Static checks failed: {', '.join(failed)}."
        return "NEEDS_REFINEMENT", f"Static checks failed: {', '.join(failed)}."
    return "STATIC_PASS_REQUIRES_LLM", "Static checks passed. Run LLM semantic judgement before LEAF_READY."


def add_route(
    routes: List[Dict[str, Any]],
    target: str,
    criterion: str,
    reason: str,
    actions: List[str],
    evidence: Optional[List[str]] = None,
) -> None:
    routes.append(
        {
            "target": target,
            "criterion": criterion,
            "reason": reason,
            "actions": actions,
            "evidence": evidence or [],
        }
    )


def refinement_routes(static_report: Dict[str, Any], llm_report: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Route Leaf Gate blockers to the artifact owner that can resolve them."""
    routes: List[Dict[str, Any]] = []

    missing = static_report["artifacts"]["missing"]
    if missing:
        artifact_targets = {
            "feature": "testcase",
            "architecture": "architecture",
            "prd": "owner_decision",
            "traceability": "testcase",
            "risks": "owner_decision",
        }
        for artifact in missing:
            target = artifact_targets.get(artifact, "owner_decision")
            add_route(
                routes,
                target,
                "artifacts",
                f"Missing required artifact: {artifact}",
                [f"Provide or regenerate `{artifact}` before rerunning Leaf Gate."],
                [artifact],
            )

    c2 = static_report["C2_contract_boundary"]
    missing_fields = c2.get("evidence", {}).get("missing_fields", [])
    if missing_fields:
        add_route(
            routes,
            "architecture",
            "C2_contract_boundary",
            "Architecture contract is missing required fields.",
            [f"Add `{field}` to the relevant architecture contract." for field in missing_fields],
            [f"missing_fields={missing_fields}"],
        )

    c4 = static_report["C4_verifiability"]
    c4_evidence = c4.get("evidence", {})
    unmapped = c4_evidence.get("unmapped_requirements", [])
    if unmapped:
        add_route(
            routes,
            "testcase",
            "C4_verifiability",
            "Current-layer requirements do not have testcase coverage.",
            [f"Add or tag testcase scenarios for {req_id}." for req_id in unmapped],
            [f"unmapped_requirements={unmapped}"],
        )

    untagged = c4_evidence.get("untagged_scenarios", [])
    if untagged:
        add_route(
            routes,
            "testcase",
            "C4_verifiability",
            "Scenarios are missing REQ/NFR trace tags.",
            [f"Add a current-layer REQ/NFR tag to scenario `{scenario}`." for scenario in untagged],
            [f"untagged_scenarios={untagged}"],
        )

    gaps = c4_evidence.get("architecture_evidence_gaps", [])
    testcase_gaps = [gap for gap in gaps if gap.endswith(": missing_testcase")]
    architecture_gaps = [
        gap
        for gap in gaps
        if gap.endswith(": missing_architecture") or gap.endswith(": weak_evidence")
    ]
    if testcase_gaps:
        add_route(
            routes,
            "testcase",
            "C4_verifiability",
            "Traceability rows are missing testcase evidence.",
            [f"Add testcase coverage for {gap.split(':', 1)[0]}." for gap in testcase_gaps],
            testcase_gaps,
        )
    if architecture_gaps:
        add_route(
            routes,
            "architecture",
            "C4_verifiability",
            "Traceability rows are missing strong or medium architecture evidence.",
            [f"Add explicit architecture evidence for {gap.split(':', 1)[0]}." for gap in architecture_gaps],
            architecture_gaps,
        )

    c5 = static_report["C5_risk_decomposition"]
    high_risks = c5.get("evidence", {}).get("unresolved_high_risks", 0)
    if high_risks:
        if testcase_gaps or unmapped:
            add_route(
                routes,
                "testcase",
                "C5_risk_decomposition",
                "Open high risks are caused by missing testcase coverage.",
                ["Close testcase coverage gaps, then rerun Leaf Gate to regenerate risks.md."],
                [f"unresolved_high_risks={high_risks}"],
            )
        if architecture_gaps:
            add_route(
                routes,
                "architecture",
                "C5_risk_decomposition",
                "Open high risks are caused by weak or missing architecture evidence.",
                ["Strengthen architecture evidence, then rerun Leaf Gate to regenerate risks.md."],
                [f"unresolved_high_risks={high_risks}"],
            )
        if not (testcase_gaps or unmapped or architecture_gaps):
            add_route(
                routes,
                "owner_decision",
                "C5_risk_decomposition",
                "Open high risks remain that cannot be resolved by artifact routing alone.",
                ["Confirm the risk disposition or provide an owner decision before rerunning Leaf Gate."],
                [f"unresolved_high_risks={high_risks}"],
            )

    if llm_report:
        explicit_llm_routes: set[str] = set()
        for route in llm_report.get("refinement_routes") or []:
            target = route.get("target")
            criterion = route.get("criterion")
            if target not in REFINEMENT_TARGETS or not criterion:
                continue
            explicit_llm_routes.add(str(criterion))
            add_route(
                routes,
                target,
                str(criterion),
                route.get("reason") or "Semantic judgement requires artifact refinement.",
                route.get("actions") or ["Resolve the semantic judgement issue, then rerun Leaf Gate."],
                route.get("evidence") or [],
            )

        judgement = llm_report.get("llm_judgement", {})
        for criterion, item in judgement.items():
            item_status = str(item.get("status", "")).lower()
            confidence = float(item.get("confidence", 0))
            if (
                item_status in {"warn", "fail"} or confidence < DEFAULT_THRESHOLDS["min_llm_confidence"]
            ) and criterion not in explicit_llm_routes:
                add_route(
                    routes,
                    "owner_decision",
                    criterion,
                    "Semantic judgement requires owner confirmation.",
                    [item.get("reason") or f"Resolve semantic judgement issue for {criterion}."],
                    item.get("evidence") or [],
                )

    return routes


def combine_with_llm(static_report: Dict[str, Any], llm_path: Path, thresholds: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    try:
        llm_report = json.loads(llm_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "NEEDS_REFINEMENT", f"LLM judgement is not valid JSON: {exc}.", {}

    judgement = llm_report.get("llm_judgement", {})
    missing = [criterion for criterion in CRITERIA if criterion not in judgement]
    if missing:
        return "NEEDS_REFINEMENT", f"LLM judgement missing criteria: {', '.join(missing)}.", llm_report

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
        return "NEEDS_REFINEMENT", "Required artifacts are missing.", llm_report
    if static_failed:
        if "C1_behavior_complexity" not in static_failed:
            return "NEEDS_REFINEMENT", f"Static checks failed: {', '.join(static_failed)}.", llm_report
        return "NEEDS_DECOMPOSITION", f"Static checks failed: {', '.join(static_failed)}.", llm_report
    if failed:
        if any(str(item).startswith("C1_behavior_complexity") for item in failed):
            return "NEEDS_DECOMPOSITION", f"LLM judgement failed: {', '.join(failed)}.", llm_report
        return "NEEDS_REFINEMENT", f"LLM judgement failed: {', '.join(failed)}.", llm_report
    if high_risks:
        return "NEEDS_REFINEMENT", "Unresolved high risks remain.", llm_report
    if low_confidence or warned:
        parts = []
        if low_confidence:
            parts.append(f"low confidence: {', '.join(low_confidence)}")
        if warned:
            parts.append(f"warnings: {', '.join(warned)}")
        return "NEEDS_REFINEMENT", "; ".join(parts), llm_report
    return "LEAF_READY", "Static checks and LLM judgement passed.", llm_report


def build_report(
    node_dir: Path,
    llm_path: Optional[Path],
    prepare: bool = True,
    prd_path: Optional[Path] = None,
    feature_path: Optional[Path] = None,
    architecture_path: Optional[Path] = None,
    traceability_path: Optional[Path] = None,
    risks_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    profile_path: Optional[Path] = None,
) -> Dict[str, Any]:
    config = load_leaf_gate_config(node_dir, config_path=config_path, profile_path=profile_path)
    thresholds = config.thresholds
    artifacts = find_artifacts(
        node_dir,
        prd_path=prd_path,
        feature_path=feature_path,
        architecture_path=architecture_path,
        traceability_path=traceability_path,
        risks_path=risks_path,
    )
    if prepare:
        artifacts = prepare_evidence(artifacts, config.profile)
    artifacts.warnings.extend(config.warnings)
    checks = static_checks(artifacts, thresholds, config.profile)
    decision, reason = static_decision(checks)
    llm_report: Dict[str, Any] = {}
    if llm_path:
        decision, reason, llm_report = combine_with_llm(checks, llm_path, thresholds)
    routes = refinement_routes(checks, llm_report)
    return {
        "node_id": node_dir.name or node_dir.resolve().name,
        "decision": decision,
        "summary": reason,
        "thresholds": thresholds,
        "config": {
            "config_path": str(config.config_path) if config.config_path else None,
            "profile_path": str(config.profile_path) if config.profile_path else None,
            "profile": config.profile.to_report(),
            "warnings": config.warnings,
        },
        "static_checks": checks,
        "llm_judgement": llm_report.get("llm_judgement"),
        "refinement_routes": routes,
        "next_action": next_action(decision, routes, checks),
    }


def candidate_decomposition(checks: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    c1_report = checks["C1_behavior_complexity"]
    c1 = c1_report["evidence"]
    c5 = checks["C5_risk_decomposition"]["evidence"]
    if "expanded case count exceeds threshold" in c1_report.get("reason", ""):
        candidates.append("split-by-behavior-family")
    if c1.get("composite_scenario_count", 0):
        candidates.append("split-composite-cross-requirement-scenarios")
    if c1.get("metric_only_scenario_count", 0):
        candidates.append("split-observability-and-metrics")
    for class_name in c5.get("high_risk_classes", []):
        candidates.append(f"isolate-{class_name.replace('_', '-')}")
    return sorted(set(candidates))


def next_action(
    decision: str,
    routes: Optional[List[Dict[str, Any]]] = None,
    checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if decision == "LEAF_READY":
        return {"type": "vibecode", "children": [], "notes": ["Proceed to implementation package."]}
    if decision == "NEEDS_DECOMPOSITION":
        children = candidate_decomposition(checks) if checks else []
        return {"type": "decompose", "children": children, "notes": ["Generate lower-layer PRDs for failed criteria."]}
    targets = sorted({route["target"] for route in routes or []})
    note = "Route refinement feedback to: " + ", ".join(targets) if targets else "Add or clarify required artifacts."
    return {"type": "refine_spec", "children": [], "notes": [note]}


def report_relative_path(path_value: Optional[str], node_dir_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    path = Path(path_value)
    node_dir = Path(node_dir_value) if node_dir_value else None
    if node_dir:
        try:
            return str(path.relative_to(node_dir)).replace("\\", "/")
        except ValueError:
            pass
    return str(path).replace("\\", "/")


def route_suggested_files(target: str, report: Dict[str, Any]) -> List[str]:
    artifacts = report.get("static_checks", {}).get("artifacts", {})
    node_dir = artifacts.get("node_dir")
    files: List[str] = []

    def add(path_value: Optional[str]) -> None:
        relative = report_relative_path(path_value, node_dir)
        if relative and relative not in files:
            files.append(relative)

    add(artifacts.get("prd"))
    if target == "architecture":
        architecture_files = artifacts.get("architecture_files") or []
        contract = next((path for path in architecture_files if Path(path).name == "06-interface-contracts.md"), None)
        add(contract or artifacts.get("architecture"))
        if artifacts.get("architecture_validation"):
            add(artifacts.get("architecture_validation"))
    elif target == "testcase":
        add(artifacts.get("feature"))
    else:
        add(artifacts.get("risks"))
        add(artifacts.get("traceability"))
    add("leaf-gate.report.json")
    return files


REFINEMENT_TARGETS = ("architecture", "testcase", "owner_decision")


def target_refinement_filename(target: str) -> str:
    return f"leaf-gate.refinement.{target}.md"


def ordered_route_targets(report: Dict[str, Any]) -> List[str]:
    present = {route.get("target") for route in report.get("refinement_routes") or []}
    return [target for target in REFINEMENT_TARGETS if target in present]


def render_refinement_index_markdown(report: Dict[str, Any]) -> str:
    targets = ordered_route_targets(report)
    lines = [
        "# Leaf Gate Refinement Index",
        "",
        f"Node: `{report.get('node_id', 'unknown')}`",
        f"Decision: `{report.get('decision', 'unknown')}`",
        f"Summary: {report.get('summary', '')}",
        "",
        "This index points each artifact owner to a target-specific Markdown handoff. Share only the matching target file with each owner.",
        "",
    ]
    if not targets:
        lines.extend(
            [
                "No target-specific refinement files were generated.",
                "",
                "Rerun Leaf Gate after any upstream artifact change.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["Target-specific files:", ""])
    for target in targets:
        lines.append(f"- `{target}`: `{target_refinement_filename(target)}`")
    lines.extend(
        [
            "",
            "Do not edit `traceability.md` or `risks.md` directly. Fix the upstream artifact, then rerun Leaf Gate.",
            "",
        ]
    )
    return "\n".join(lines)


def render_refinement_markdown(report: Dict[str, Any], target: Optional[str] = None) -> str:
    routes = report.get("refinement_routes") or []
    if target:
        routes = [route for route in routes if route.get("target") == target]
    header = "# Leaf Gate Refinement Suggestions"
    if target:
        header = f"{header}: {target}"
    lines = [
        header,
        "",
        f"Node: `{report.get('node_id', 'unknown')}`",
        f"Decision: `{report.get('decision', 'unknown')}`",
        f"Summary: {report.get('summary', '')}",
        "",
        "This file is generated from `leaf-gate.report.json` for artifact owners. Do not edit `traceability.md` or `risks.md` directly; fix the upstream PRD, architecture, testcase, or owner decision input, then rerun Leaf Gate.",
        "",
    ]

    if not routes:
        lines.extend(
            [
                "No refinement routes were produced.",
                "",
                "Rerun Leaf Gate after any upstream artifact change.",
                "",
            ]
        )
        return "\n".join(lines)

    targets = [target] if target else REFINEMENT_TARGETS
    for current_target in targets:
        target_routes = [route for route in routes if route.get("target") == current_target]
        if not target_routes:
            continue
        lines.extend([f"## {current_target}", "", "Suggested files to edit or review:"])
        for path in route_suggested_files(current_target, report):
            lines.append(f"- `{path}`")
        lines.append("")
        for index, route in enumerate(target_routes, start=1):
            lines.extend(
                [
                    f"### {index}. {route.get('criterion', 'unknown')}",
                    "",
                    f"Reason: {route.get('reason', '')}",
                    "",
                    "Actions:",
                ]
            )
            for action in route.get("actions") or ["Clarify or regenerate the upstream artifact."]:
                lines.append(f"- {action}")
            evidence = route.get("evidence") or []
            if evidence:
                lines.extend(["", "Evidence:"])
                for item in evidence:
                    lines.append(f"- `{item}`")
            lines.append("")

    lines.extend(
        [
            "## Rerun Leaf Gate",
            "",
            "After applying the changes, rerun Leaf Gate for this node and replace `leaf-gate.report.json`. The generated `traceability.md`, `risks.md`, and this Markdown suggestion file should be regenerated from the fixed upstream artifacts.",
            "",
        ]
    )
    return "\n".join(lines)


def render_decomposition_markdown(report: Dict[str, Any]) -> str:
    checks = report.get("static_checks", {})
    c1 = checks.get("C1_behavior_complexity", {})
    c3 = checks.get("C3_ai_context_control", {})
    c5 = checks.get("C5_risk_decomposition", {})
    children = report.get("next_action", {}).get("children") or []
    lines = [
        "# Leaf Gate Decomposition Suggestions",
        "",
        f"Node: `{report.get('node_id', 'unknown')}`",
        f"Decision: `{report.get('decision', 'unknown')}`",
        f"Summary: {report.get('summary', '')}",
        "",
        "Why decomposition is recommended:",
        f"- C1: {c1.get('reason', '')}",
        f"- C3: {c3.get('reason', '')}",
        f"- C5: {c5.get('reason', '')}",
        "",
        "Recommended child-node cuts:",
    ]
    if children:
        lines.extend(f"- `{child}`" for child in children)
    else:
        lines.append("- Split by behavior family and rerun Leaf Gate on each child node.")
    lines.extend(["", "Evidence summary:"])
    for key in ("scenario_count", "scenario_points", "composite_scenario_count", "metric_only_scenario_count"):
        value = c1.get("evidence", {}).get(key)
        if value is not None:
            lines.append(f"- `{key}`: {value}")
    for key in ("implementation_pack_tokens", "full_artifact_tokens"):
        value = c3.get("evidence", {}).get(key)
        if value is not None:
            lines.append(f"- `{key}`: {value}")
    high_risks = c5.get("evidence", {}).get("high_risk_classes") or []
    if high_risks:
        lines.append(f"- `high_risk_classes`: {', '.join(high_risks)}")
    lines.extend(["", "After creating child nodes, run Leaf Gate on each child before vibe coding.", ""])
    return "\n".join(lines)


def write_refinement_markdown_files(report: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for target in REFINEMENT_TARGETS:
        stale = output_dir / target_refinement_filename(target)
        if stale.exists():
            stale.unlink()
    decomposition = output_dir / "leaf-gate.decomposition.md"
    if decomposition.exists():
        decomposition.unlink()

    (output_dir / "leaf-gate.refinement.md").write_text(
        render_refinement_index_markdown(report),
        encoding="utf-8",
    )
    for target in ordered_route_targets(report):
        (output_dir / target_refinement_filename(target)).write_text(
            render_refinement_markdown(report, target=target),
            encoding="utf-8",
        )
    if report.get("decision") == "NEEDS_DECOMPOSITION":
        decomposition.write_text(render_decomposition_markdown(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Leaf Gate static checks for a PRD node.")
    parser.add_argument("node_dir", type=Path, help="Directory containing PRD node artifacts.")
    parser.add_argument("--output", type=Path, help="Where to write report JSON. Defaults to stdout.")
    parser.add_argument("--llm-judgement", type=Path, help="Optional LLM judgement JSON to combine with static checks.")
    parser.add_argument("--skip-prepare", action="store_true", help="Skip generated traceability.md and risks.md refresh.")
    parser.add_argument("--prd", type=Path, help="Explicit PRD path, relative to node_dir unless absolute.")
    parser.add_argument("--feature", type=Path, help="Explicit .feature path, relative to node_dir unless absolute.")
    parser.add_argument("--architecture", type=Path, help="Explicit architecture file or directory, relative to node_dir unless absolute.")
    parser.add_argument("--traceability", type=Path, help="Explicit traceability path, relative to node_dir unless absolute.")
    parser.add_argument("--risks", type=Path, help="Explicit risks path, relative to node_dir unless absolute.")
    parser.add_argument("--config", type=Path, help="Explicit Leaf Gate config JSON path, relative to node_dir unless absolute.")
    parser.add_argument("--profile", type=Path, help="Explicit project profile JSON path, relative to node_dir unless absolute.")
    args = parser.parse_args()

    if not args.node_dir.exists() or not args.node_dir.is_dir():
        raise SystemExit(f"Node directory does not exist: {args.node_dir}")

    report = build_report(
        args.node_dir,
        args.llm_judgement,
        prepare=not args.skip_prepare,
        prd_path=args.prd,
        feature_path=args.feature,
        architecture_path=args.architecture,
        traceability_path=args.traceability,
        risks_path=args.risks,
        config_path=args.config,
        profile_path=args.profile,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        write_refinement_markdown_files(report, args.output.parent)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
