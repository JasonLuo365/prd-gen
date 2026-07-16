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

FINAL_DECISIONS = {"CONTINUE_LAYERING", "STOP_LAYERING"}

CURRENT_REQ_ID_RE = r"(?:REQ|NFR|UC|QAS)-(?:[A-Z]+)?\d{3,}"
TRACE_TAG_ID_RE = r"(?:REQ|NFR|UC|QAS|MET)-(?:[A-Z]+)?\d{3,}"


class LeafGateInputError(ValueError):
    """The upstream node is not ready for a layering decision."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_report(self) -> Dict[str, Any]:
        return {
            "status": "INPUT_ERROR",
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


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
    architecture_validation_files: List[Path] = field(default_factory=list)
    architecture_supporting_files: List[Path] = field(default_factory=list)
    architecture_remediation_files: List[Path] = field(default_factory=list)
    architecture_manifest: Optional[Path] = None
    architecture_selection: str = ""
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


ARCHITECTURE_SUFFIXES = {".md", ".markdown", ".json", ".yaml", ".yml"}
MANIFEST_NAMES = {"readme", "index", "manifest", "contents", "目录", "索引", "清单"}


def architecture_files_in(path: Path, recursive: bool = False) -> List[Path]:
    iterator = path.rglob("*") if recursive else path.glob("*")
    return sorted(
        file
        for file in iterator
        if file.is_file()
        and file.suffix.lower() in ARCHITECTURE_SUFFIXES
        and not file.name.startswith("leaf-gate.")
    )


def is_manifest(path: Path) -> bool:
    stem = path.stem.lower()
    return stem in MANIFEST_NAMES or bool(re.search(r"(?:^|[-_])manifest$", stem))


def manifest_links(manifest: Path, package_root: Path) -> List[Path]:
    links: List[Path] = []
    manifest_text = read_text(manifest)
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", manifest_text)
    targets.extend(
        match.group(1)
        for match in re.finditer(
            r"(?:^|[\s:\"'])[- ]*([A-Za-z0-9_./\\-]+\.(?:md|markdown|json|ya?ml))(?=$|[\s,\"'])",
            manifest_text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )
    for target in targets:
        target = target.strip().strip("<>").split("#", 1)[0]
        if not target or re.match(r"^[a-z]+://", target, flags=re.IGNORECASE):
            continue
        candidate = manifest.parent / target
        resolved = candidate.resolve()
        try:
            resolved.relative_to(package_root.resolve())
        except ValueError:
            continue
        if candidate.is_file() and candidate.suffix.lower() in ARCHITECTURE_SUFFIXES:
            links.append(candidate)
    return sorted(set(links))


def remediation_artifact(path: Path, text: str = "") -> bool:
    value = f"{path.name}\n{text[:500]}"
    return bool(
        re.search(
            r"remediation|modification[-_ ]plan|change[-_ ]plan|整改|修改方案|修正方案|改进计划",
            value,
            flags=re.IGNORECASE,
        )
    )


def validation_artifact(path: Path, text: str = "") -> bool:
    value = f"{path.name}\n{text[:500]}"
    return bool(
        re.search(
            r"validation[-_ ]report|architecture[-_ ]validation|verification[-_ ]report|review[-_ ]report|架构验证|验证报告|评审报告|验收报告",
            value,
            flags=re.IGNORECASE,
        )
    )


def package_semantic_score(path: Path, files: List[Path], linked: List[Path]) -> int:
    sample = "\n".join(f"{file.name}\n{read_text(file)[:1200]}" for file in files[:20])
    concepts = (
        r"system overview|系统概览|系统上下文",
        r"runtime|运行时|时序",
        r"data|consistency|数据|一致性",
        r"interface|contract|接口|契约",
        r"decision|technology|决策|技术",
        r"deployment|部署",
    )
    score = len(linked) * 12 + sum(3 for pattern in concepts if re.search(pattern, sample, re.IGNORECASE))
    if path.name.lower() in {"output", "final", "deliverables", "package", "交付", "最终输出"}:
        score += 4
    return score + min(len(files), 10)


def select_architecture_package(path: Path) -> Tuple[Path, List[Path], Optional[Path], str]:
    candidates: List[Tuple[int, Path, List[Path], Optional[Path], List[Path]]] = []
    directories = [path] + sorted(directory for directory in path.rglob("*") if directory.is_dir())
    for directory in directories:
        direct_files = architecture_files_in(directory)
        if not direct_files:
            continue
        manifests = [file for file in direct_files if is_manifest(file)]
        manifest = manifests[0] if manifests else None
        linked = manifest_links(manifest, path) if manifest else []
        usable = [file for file in direct_files if not remediation_artifact(file, read_text(file)) and not validation_artifact(file, read_text(file))]
        linked = [
            file
            for file in linked
            if not remediation_artifact(file, read_text(file)) and not validation_artifact(file, read_text(file))
        ]
        if not usable:
            continue
        candidates.append((package_semantic_score(directory, usable, linked), directory, usable, manifest, linked))

    if not candidates:
        return path, [], None, "empty-directory"
    _, source_dir, usable, manifest, linked = max(candidates, key=lambda item: (item[0], -len(item[1].parts)))
    if linked:
        primary = linked
        selection = "manifest-links"
    else:
        primary = [file for file in usable if not is_manifest(file)] or usable
        selection = "semantic-package"
    if manifest and manifest not in primary:
        primary = [manifest, *primary]
    return source_dir, sorted(set(primary)), manifest, selection


def architecture_dir_artifacts(
    path: Path,
) -> Tuple[Path, List[Path], List[Path], List[Path], List[Path], Optional[Path], str]:
    source_dir, primary, manifest, selection = select_architecture_package(path)
    all_files = architecture_files_in(path, recursive=True)
    validation: List[Path] = []
    remediation: List[Path] = []
    for file in all_files:
        text = read_text(file)
        if remediation_artifact(file, text):
            remediation.append(file)
        elif validation_artifact(file, text):
            validation.append(file)
    supporting = [file for file in all_files if file not in primary and file not in validation and file not in remediation]
    return source_dir, primary, validation, supporting, remediation, manifest, selection


def find_architecture_artifacts(
    node_dir: Path, architecture_path: Optional[Path] = None
) -> Tuple[Optional[Path], List[Path], List[Path], List[Path], List[Path], Optional[Path], str]:
    explicit = resolve_path(node_dir, architecture_path)
    if explicit:
        if explicit.is_file():
            return explicit, [explicit], [], [], [], None, "explicit-file"
        if explicit.is_dir():
            return architecture_dir_artifacts(explicit)
        return None, [], [], [], [], None, "not-found"

    architecture_file = find_first(
        node_dir,
        ["architecture.yaml", "architecture.yml", "architecture.json", "architecture.md"],
        [],
    )
    if architecture_file:
        return architecture_file, [architecture_file], [], [], [], None, "conventional-file"

    for name in ("architecture", "output"):
        architecture_dir = node_dir / name
        if architecture_dir.exists() and architecture_dir.is_dir():
            source_dir, files, validation, supporting, remediation, manifest, selection = architecture_dir_artifacts(architecture_dir)
            if files:
                return source_dir, files, validation, supporting, remediation, manifest, selection

    architecture_file = find_first(
        node_dir,
        [],
        ["*architecture*.yaml", "*architecture*.yml", "*architecture*.json", "*architecture*.md", "*arch*.md"],
    )
    if architecture_file:
        return architecture_file, [architecture_file], [], [], [], None, "matched-file"
    return None, [], [], [], [], None, "not-found"


def find_artifacts(
    node_dir: Path,
    prd_path: Optional[Path] = None,
    feature_path: Optional[Path] = None,
    architecture_path: Optional[Path] = None,
    traceability_path: Optional[Path] = None,
    risks_path: Optional[Path] = None,
) -> ArtifactSet:
    warnings: List[str] = []
    (
        architecture,
        architecture_files,
        architecture_validation_files,
        architecture_supporting_files,
        architecture_remediation_files,
        architecture_manifest,
        architecture_selection,
    ) = find_architecture_artifacts(node_dir, architecture_path)
    architecture_validation = architecture_validation_files[0] if architecture_validation_files else None
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
        architecture_validation_files=architecture_validation_files,
        architecture_supporting_files=architecture_supporting_files,
        architecture_remediation_files=architecture_remediation_files,
        architecture_manifest=architecture_manifest,
        architecture_selection=architecture_selection,
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

    in_deferred_section = False
    for line in prd_text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            in_deferred_section = bool(
                re.search(
                    r"could have|future backlog|documented exclusions?|out[-_ ]of[-_ ]version|未来|后续版本|范围外|明确排除",
                    title,
                    flags=re.IGNORECASE,
                )
            )
            continue
        if in_deferred_section or re.search(
            r"out[-_ ]of[-_ ]version|release_scope\s*[:=]\s*(?:future|excluded)|\|\s*(?:future|out_of_version|excluded|deferred)\s*\|",
            line,
            flags=re.IGNORECASE,
        ):
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
        explicit_refs = extract_explicit_requirement_refs(text)
        if normalize_requirement_ref(req_id) in explicit_refs:
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
            if strength == "strong" and normalize_requirement_ref(req_id) in explicit_refs:
                shown_terms = "explicit requirement allocation"
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


def normalize_requirement_ref(value: str, default_prefix: str = "REQ") -> str:
    match = re.fullmatch(r"(?:(REQ|NFR|FR|UC|QAS)-)?(D)?(\d{3,})", value.strip(), re.IGNORECASE)
    if not match:
        return value.upper()
    prefix = (match.group(1) or default_prefix).upper()
    derived = "D" if match.group(2) else ""
    return f"{prefix}-{derived}{int(match.group(3)):03d}"


def extract_explicit_requirement_refs(text: str) -> set[str]:
    """Expand explicit current-layer references such as D001~D007 and NFR-D001~003."""
    refs: set[str] = set()
    pattern = re.compile(
        r"(?<![A-Za-z0-9])"
        r"(?:(?P<prefix>REQ|NFR|FR|UC|QAS)-)?"
        r"(?P<derived>D)?(?P<start>\d{3,})"
        r"(?:\s*[~–—-]\s*(?:(?P<end_prefix>REQ|NFR|FR|UC|QAS)-)?"
        r"(?P<end_derived>D)?(?P<end>\d{3,}))?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        prefix = (match.group("prefix") or match.group("end_prefix") or "REQ").upper()
        derived = bool(match.group("derived") or match.group("end_derived"))
        start = int(match.group("start"))
        end = int(match.group("end")) if match.group("end") else start
        if end < start or end - start > 999:
            end = start
        for number in range(start, end + 1):
            refs.add(f"{prefix}-{'D' if derived else ''}{number:03d}")
    return refs


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
    risk_sources = [*artifacts.architecture_validation_files, *artifacts.architecture_files]
    for item in extract_validation_risk_rows(risk_sources, artifacts.node_dir):
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
            "> Generated by Leaf Gate prepare evidence from traceability gaps, the validated primary architecture, and optional validation evidence.",
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
    architecture_validation_files: Iterable[Path],
    traceability_text: str,
    risk_text: str,
) -> str:
    selected = [prd_text, feature_text, traceability_text, risk_text]
    wanted = ("contract", "interface", "接口", "契约", "data-model", "runtime", "validation")
    for path in architecture_files:
        name = path.name.lower()
        text = read_text(path)
        if any(term in name for term in wanted) or re.search(r"运行时|接口|契约|数据|一致性", text[:1200]):
            selected.append(text)
    selected.extend(read_text(path) for path in architecture_validation_files)
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
        implementation_pack_text(
            prd_text,
            feature_text,
            artifacts.architecture_files,
            artifacts.architecture_validation_files,
            traceability_text,
            risk_text,
        )
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
            "architecture_validation_files": [str(path) for path in artifacts.architecture_validation_files],
            "architecture_supporting_files": [str(path) for path in artifacts.architecture_supporting_files],
            "architecture_remediation_files": [str(path) for path in artifacts.architecture_remediation_files],
            "architecture_manifest": str(artifacts.architecture_manifest) if artifacts.architecture_manifest else None,
            "architecture_selection": artifacts.architecture_selection,
            "traceability": str(artifacts.traceability) if artifacts.traceability else None,
            "risks": str(artifacts.risks) if artifacts.risks else None,
            "missing": missing_artifacts,
            "warnings": artifacts.warnings,
            "inventory": {
                "traceability_source": "provided" if artifacts.traceability else "missing",
                "risks_source": "provided" if artifacts.risks else "missing",
                "architecture_package": str(artifacts.architecture) if artifacts.architecture else None,
                "architecture_primary_count": len(artifacts.architecture_files),
                "architecture_validation_count": len(artifacts.architecture_validation_files),
                "architecture_supporting_count": len(artifacts.architecture_supporting_files),
                "architecture_remediation_count": len(artifacts.architecture_remediation_files),
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


def assert_layering_preconditions(report: Dict[str, Any]) -> None:
    """Reject upstream completeness problems without turning them into layering decisions."""
    problems: Dict[str, Any] = {}
    missing = report["artifacts"]["missing"]
    if missing:
        problems["missing_artifacts"] = missing

    missing_fields = report["C2_contract_boundary"].get("evidence", {}).get("missing_fields", [])
    if missing_fields:
        problems["missing_contract_fields"] = missing_fields

    c3 = report["C3_ai_context_control"].get("evidence", {})
    if c3.get("open_questions", 0):
        problems["open_questions"] = c3["open_questions"]
    if c3.get("todo_markers", 0):
        problems["todo_markers"] = c3["todo_markers"]

    c4 = report["C4_verifiability"].get("evidence", {})
    for key in ("unmapped_requirements", "architecture_evidence_gaps", "untagged_scenarios"):
        if c4.get(key):
            problems[key] = c4[key]

    unresolved_high = report["C5_risk_decomposition"].get("evidence", {}).get("unresolved_high_risks", 0)
    if unresolved_high:
        problems["unresolved_high_risks"] = unresolved_high

    if problems:
        raise LeafGateInputError(
            "UPSTREAM_VALIDATION_INCOMPLETE",
            "The PRD, testcase, and validated architecture package are not ready for a layering decision.",
            problems,
        )


def static_layering_signal(report: Dict[str, Any]) -> Tuple[Optional[str], str]:
    c1 = report["C1_behavior_complexity"]
    c3 = report["C3_ai_context_control"]
    decomposition_reasons: List[str] = []
    if c1["status"] == "fail":
        decomposition_reasons.append(c1["reason"])
    c3_reason = c3.get("reason", "")
    if re.search(r"context exceeds threshold", c3_reason, flags=re.IGNORECASE):
        decomposition_reasons.append(c3_reason)
    if decomposition_reasons:
        return "CONTINUE_LAYERING", "; ".join(decomposition_reasons)
    return None, "Static evidence is ready for semantic decomposition-gain judgement."


def combine_with_llm(static_report: Dict[str, Any], llm_path: Path, thresholds: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    try:
        llm_report = json.loads(llm_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LeafGateInputError("INVALID_SEMANTIC_JUDGEMENT", f"LLM judgement is not valid JSON: {exc}.") from exc

    judgement = llm_report.get("llm_judgement", {})
    missing = [criterion for criterion in CRITERIA if criterion not in judgement]
    if missing:
        raise LeafGateInputError(
            "INVALID_SEMANTIC_JUDGEMENT",
            f"LLM judgement is missing criteria: {', '.join(missing)}.",
            {"missing_criteria": missing},
        )

    low_confidence = []
    failed = []
    malformed = []
    for criterion in CRITERIA:
        item = judgement[criterion]
        item_status = str(item.get("status", "")).lower()
        confidence = float(item.get("confidence", 0))
        evidence = item.get("evidence") or []
        if not evidence:
            malformed.append(f"{criterion}: missing evidence")
        if item_status == "fail":
            failed.append(criterion)
        elif item_status != "pass":
            malformed.append(f"{criterion}: invalid status {item_status!r}")
        if confidence < thresholds["min_llm_confidence"]:
            low_confidence.append(criterion)

    if low_confidence:
        raise LeafGateInputError(
            "INVALID_SEMANTIC_JUDGEMENT",
            f"Semantic judgement confidence is below threshold: {', '.join(low_confidence)}.",
            {"low_confidence": low_confidence},
        )
    recommended = llm_report.get("recommended_decision")
    if recommended is not None and recommended not in FINAL_DECISIONS:
        malformed.append(f"recommended_decision: invalid value {recommended!r}")
    if malformed:
        raise LeafGateInputError(
            "INVALID_SEMANTIC_JUDGEMENT",
            "Semantic judgement must use pass/fail with evidence and a binary recommendation.",
            {"problems": malformed},
        )
    if failed:
        return "CONTINUE_LAYERING", f"Further layering has material benefit: {', '.join(failed)}.", llm_report
    return "STOP_LAYERING", "Further layering has no material benefit.", llm_report


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
    assert_layering_preconditions(checks)
    decision, reason = static_layering_signal(checks)
    llm_report: Dict[str, Any] = {}
    if llm_path:
        semantic_decision, semantic_reason, llm_report = combine_with_llm(checks, llm_path, thresholds)
        if decision != "CONTINUE_LAYERING":
            decision, reason = semantic_decision, semantic_reason
    return {
        "node_id": node_dir.name or node_dir.resolve().name,
        "phase": "FINAL" if decision in FINAL_DECISIONS else "STATIC_EVIDENCE",
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
        "next_action": next_action(decision, checks),
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
    decision: Optional[str],
    checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if decision == "STOP_LAYERING":
        return {"type": "vibecode", "children": [], "notes": ["Proceed to implementation package."]}
    if decision == "CONTINUE_LAYERING":
        children = candidate_decomposition(checks) if checks else []
        return {"type": "decompose", "children": children, "notes": ["Generate lower-layer PRDs for failed criteria."]}
    return {
        "type": "semantic_judgement",
        "children": [],
        "notes": ["Run the LLM decomposition-gain judgement to obtain a final binary decision."],
    }


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


def write_decision_markdown_files(report: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    decomposition = output_dir / "leaf-gate.decomposition.md"
    if decomposition.exists():
        decomposition.unlink()
    if report.get("decision") == "CONTINUE_LAYERING":
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

    try:
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
    except LeafGateInputError as exc:
        error_payload = json.dumps(exc.to_report(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(error_payload, encoding="utf-8")
        else:
            print(error_payload, end="")
        return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        write_decision_markdown_files(report, args.output.parent)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
