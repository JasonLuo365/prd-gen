"""Parse parent PRD and architecture inputs for Derive mode."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from prd_flow import yaml_utils as yaml


STANDARD_ARCH_FILES = [
    "README.md",
    "01-system-overview.md",
    "02-module-partitioning.md",
    "03-runtime-architecture.md",
    "04-adr-summary.md",
    "05-data-model.md",
    "06-interface-contracts.md",
    "07-technology-choices.md",
    "08-deployment.md",
]

VALID_GRANULARITIES = {"auto", "deployable_module", "bounded_context", "component"}

EXTERNAL_NAMES = [
    "Telegram Bot API",
    "Telegram",
    "PC OS / Applications",
    "PC OS / Apps",
    "SMS Gateway",
    "Object Storage",
    "LLM Service",
    "Math Recognition Service",
    "OCR Service",
    "PostgreSQL",
    "Redis",
    "Kafka",
    "RabbitMQ",
    "Redis Streams",
    "S3",
    "MinIO",
]


def parse_parent_prd(path: Path) -> dict:
    """Parse a parent PRD document and extract structured data."""
    content = path.read_text(encoding="utf-8")

    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            body = parts[2]
            loaded = yaml.safe_load(fm)
            if loaded is not None:
                frontmatter = loaded
            content = body

    requirements = []
    non_functional = []
    current_priority = "Must Have"
    last_requirement: dict[str, Any] | None = None
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            last_requirement = None
            continue
        heading = stripped.lstrip("#").strip()
        if heading in {"Must Have", "Should Have", "Could Have"}:
            current_priority = heading
            last_requirement = None
            continue

        req_match = re.match(r"- \[(REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*)\]\s+(.+)$", stripped)
        if req_match:
            last_requirement = {
                "id": req_match.group(1),
                "text": req_match.group(2).strip(),
                "priority": current_priority,
            }
            requirements.append(last_requirement)
            continue

        nfr_match = re.match(r"- \[(NFR-[A-Z0-9]+(?:-[A-Z0-9]+)*)\]\s+(.+)$", stripped)
        if nfr_match:
            last_requirement = {
                "id": nfr_match.group(1),
                "text": nfr_match.group(2).strip(),
            }
            non_functional.append(last_requirement)
            continue

        metadata_match = re.match(
            r"-\s+(parent_req|parent_nfr|source_kind|implementation_surfaces|related_reqs|release_scope|requirement_kind|scope_reason):\s*(.+)$",
            stripped,
        )
        if last_requirement is not None and line[:1].isspace() and metadata_match:
            key = metadata_match.group(1)
            value = metadata_match.group(2).strip()
            if key in {"implementation_surfaces", "related_reqs"}:
                value = value.strip("[]")
                last_requirement[key] = [item.strip() for item in value.split(",") if item.strip()]
            else:
                last_requirement[key] = value
            continue

        last_requirement = None

    return {
        "doc_id": frontmatter.get("doc_id", "UNKNOWN") if isinstance(frontmatter, dict) else "UNKNOWN",
        "frontmatter": frontmatter,
        "requirements": requirements,
        "non_functional": non_functional,
        "acceptance_contracts": _parse_acceptance_contracts(content),
        # Legacy input remains readable, but new output never emits Gherkin here.
        "acceptance_scenarios": _parse_gherkin_scenarios(content),
        "success_metrics": _parse_success_metrics(content),
        "non_goals": _parse_non_goals(content),
        "raw_content": content,
    }


def _parse_acceptance_contracts(content: str) -> list[dict[str, Any]]:
    """Parse the explicit Acceptance Contracts Markdown section."""
    heading = re.search(r"^#\s+Acceptance Contracts\s*$", content, re.MULTILINE | re.IGNORECASE)
    if not heading:
        return []
    next_section = re.search(r"^#\s+", content[heading.end():], re.MULTILINE)
    end = heading.end() + next_section.start() if next_section else len(content)
    section = content[heading.end():end]
    contracts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    list_fields = {"verifies", "preconditions", "response", "observable_oracles", "boundaries", "exceptions", "exclusions", "evidence_refs"}
    for raw_line in section.splitlines():
        stripped = raw_line.strip()
        contract_match = re.match(r"^##\s+((?:AC|NFR-AC)-[A-Z0-9-]+)\s*$", stripped, re.IGNORECASE)
        if contract_match:
            if current:
                contracts.append(current)
            current = {"id": contract_match.group(1).upper()}
            continue
        field_match = re.match(r"^-\s+([a-z_]+):\s*(.*)$", stripped)
        if current is None or not field_match:
            continue
        key, value = field_match.group(1), field_match.group(2).strip()
        if key in list_fields:
            value = value.strip("[]")
            separator = "|" if "|" in value else ","
            current[key] = [item.strip() for item in value.split(separator) if item.strip()]
        else:
            current[key] = value
    if current:
        contracts.append(current)
    return contracts


def _parse_gherkin_scenarios(content: str) -> list[dict[str, Any]]:
    """Parse fenced Gherkin without discarding tags or multi-step detail."""
    scenarios: list[dict[str, Any]] = []
    in_gherkin = False
    feature = ""
    pending_tags: list[str] = []
    current: dict[str, Any] | None = None

    def finish_current() -> None:
        nonlocal current
        if current is None:
            return
        requirement_ids = [
            tag
            for tag in current.get("tags", [])
            if re.fullmatch(r"(?:REQ|NFR)-[A-Z0-9]+(?:-[A-Z0-9]+)*", tag)
        ]
        if not requirement_ids:
            scenario_name = current.get("scenario", "")
            derived_match = re.match(
                r"((?:REQ|NFR)-[A-Z0-9]+(?:-[A-Z0-9]+)*)\s+覆盖父需求",
                scenario_name,
            )
            requirement_ids = (
                [derived_match.group(1)]
                if derived_match
                else re.findall(
                    r"\b(?:REQ|NFR)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b",
                    scenario_name,
                )
            )
        current["requirement_ids"] = _unique(requirement_ids)
        scenarios.append(current)
        current = None

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.lower().startswith("```gherkin"):
            in_gherkin = True
            continue
        if in_gherkin and stripped.startswith("```"):
            finish_current()
            in_gherkin = False
            pending_tags = []
            continue
        if not in_gherkin or not stripped:
            continue

        if stripped.startswith("@"):
            pending_tags = [token[1:] for token in stripped.split() if token.startswith("@")]
            continue
        if stripped.lower().startswith("feature:"):
            finish_current()
            feature = stripped.split(":", 1)[1].strip()
            continue
        if stripped.lower().startswith("scenario:"):
            finish_current()
            current = {
                "feature": feature,
                "scenario": stripped.split(":", 1)[1].strip(),
                "tags": pending_tags,
                "steps": [],
            }
            pending_tags = []
            continue

        step_match = re.match(r"^(Given|When|Then|And|But)\s+(.+)$", stripped, re.IGNORECASE)
        if current is not None and step_match:
            keyword = step_match.group(1).capitalize()
            current["steps"].append({"keyword": keyword, "text": step_match.group(2).strip()})

    if in_gherkin:
        finish_current()
    return scenarios


def _parse_success_metrics(content: str) -> list[dict[str, str]]:
    heading = re.search(r"^#\s+Success Metrics\s*$", content, re.MULTILINE | re.IGNORECASE)
    if not heading:
        return []
    next_section = re.search(r"^#\s+", content[heading.end():], re.MULTILINE)
    end = heading.end() + next_section.start() if next_section else len(content)
    section = content[heading.end():end]
    metrics: list[dict[str, str]] = []
    for line in section.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 3:
            continue
        name = _clean_markdown(cells[0])
        if name.casefold() in {"指标", "metric", "name"}:
            continue
        metric_id = re.match(r"(MET-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b", name, re.IGNORECASE)
        metrics.append(
            {
                "id": metric_id.group(1).upper() if metric_id else "",
                "name": name,
                "target": _clean_markdown(cells[1]),
                "method": _clean_markdown(" | ".join(cells[2:])),
            }
        )
    return metrics


def _parse_non_goals(content: str) -> list[str]:
    heading = re.search(
        r"^##\s+.*(?:Non-goals|不涉及).*$",
        content,
        re.MULTILINE | re.IGNORECASE,
    )
    if not heading:
        return []
    next_heading = re.search(r"^##\s+", content[heading.end():], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(content)
    result = []
    for line in content[heading.end():end].splitlines():
        match = re.match(r"\s*-\s+(.+)$", line)
        if match:
            result.append(_clean_markdown(match.group(1)))
    return result


def extract_module_context(
    arch_path: Path,
    target_module: str,
    target_granularity: str = "auto",
) -> dict:
    """Extract context for a module from a legacy architecture file or package.

    `arch_path` may be one of:
    - legacy YAML architecture file with a top-level `modules` list;
    - architecture package directory;
    - README.md inside an architecture package;
    - zip file containing the architecture Markdown files.
    """
    if target_granularity not in VALID_GRANULARITIES:
        raise ValueError(f"Invalid target_granularity: {target_granularity}")

    source = _load_architecture_source(arch_path)
    if source["kind"] == "missing":
        return _not_found(target_module, [], source["error"], target_granularity)
    if source["kind"] == "legacy_yaml":
        return _extract_from_legacy_yaml(source, target_module, target_granularity)
    return _extract_from_markdown_package(source, target_module, target_granularity)


def extract_architecture_catalog(
    arch_path: Path,
    target_granularity: str,
) -> dict[str, Any]:
    """Return all candidate owners and architecture obligations for one layer."""
    if target_granularity not in VALID_GRANULARITIES:
        raise ValueError(f"Invalid target_granularity: {target_granularity}")

    source = _load_architecture_source(arch_path)
    if source["kind"] == "missing":
        return {
            "units": [],
            "available_modules": [],
            "architecture_coverage_gaps": [source["error"]],
            "source_files": [],
        }
    if source["kind"] == "legacy_yaml":
        units = []
        for raw_module in source.get("data", {}).get("modules", []):
            if not isinstance(raw_module, dict) or not raw_module.get("name"):
                continue
            module = dict(raw_module)
            module.setdefault("granularity", "deployable_module")
            units.append(module)
        return {
            "units": units,
            "available_modules": [unit["name"] for unit in units],
            "architecture_coverage_gaps": [],
            "source_files": list(source.get("files", {}).keys()),
        }
    return _build_markdown_catalog(source, target_granularity)


def _load_architecture_source(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "kind": "missing",
            "source_id": "UNKNOWN",
            "files": {},
            "error": f"Architecture input not found: {path}",
        }

    if path.is_file() and path.suffix.lower() == ".zip":
        return _read_zip_package(path)

    if path.is_dir():
        return _read_directory_package(path)

    content = _read_text(path)
    data = _try_load_yaml(content)
    if isinstance(data, dict) and isinstance(data.get("modules"), list):
        return {
            "kind": "legacy_yaml",
            "source_id": data.get("doc_id", path.stem),
            "path": str(path),
            "data": data,
            "files": {path.name: content},
        }

    if path.name.lower() == "readme.md":
        return _read_directory_package(path.parent, explicit_readme=path)

    return {
        "kind": "markdown_package",
        "source_id": path.stem,
        "path": str(path),
        "files": {path.name: content},
    }


def _read_directory_package(path: Path, explicit_readme: Path | None = None) -> dict[str, Any]:
    files: dict[str, str] = {}
    for name in STANDARD_ARCH_FILES:
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            files[name] = _read_text(candidate)

    if explicit_readme and explicit_readme.exists():
        files["README.md"] = _read_text(explicit_readme)

    if not files and (path / "output").is_dir():
        return _read_directory_package(path / "output")

    if not files:
        for candidate in sorted(path.glob("*.md")):
            files[candidate.name] = _read_text(candidate)

    return {
        "kind": "markdown_package",
        "source_id": path.name or "ARCH-PACKAGE",
        "path": str(path),
        "files": files,
    }


def _read_zip_package(path: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.namelist() if not m.endswith("/")]
        markdown_members = [m for m in members if Path(m).suffix.lower() == ".md"]

        for name in STANDARD_ARCH_FILES:
            match = next((m for m in markdown_members if Path(m).name == name), None)
            if match:
                files[name] = archive.read(match).decode("utf-8", errors="replace")

        if not files:
            for member in markdown_members:
                member_path = Path(member)
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                files[member_path.name] = archive.read(member).decode("utf-8", errors="replace")

    return {
        "kind": "markdown_package",
        "source_id": path.stem,
        "path": str(path),
        "files": files,
    }


def _extract_from_legacy_yaml(source: dict[str, Any], target_module: str, target_granularity: str) -> dict:
    data = source["data"]
    modules = data.get("modules", [])
    available = [m["name"] for m in modules if isinstance(m, dict) and "name" in m]

    for module in modules:
        if isinstance(module, dict) and _same_name(module.get("name", ""), target_module):
            resolved = dict(module)
            resolved.setdefault(
                "granularity",
                "deployable_module" if target_granularity == "auto" else target_granularity,
            )
            return {
                "found": True,
                "module": resolved,
                "available_modules": available,
                "parent_arch_id": source["source_id"],
                "source_files": list(source.get("files", {}).keys()),
                "target_granularity": resolved["granularity"],
            }

    return _not_found(target_module, available, None, target_granularity)


def _extract_from_markdown_package(source: dict[str, Any], target_module: str, target_granularity: str) -> dict:
    catalog = _build_markdown_catalog(source, target_granularity)
    candidates = catalog["units"]
    available_modules = catalog["available_modules"]

    exact_matches = [item for item in candidates if _same_name(item["name"], target_module)]
    if target_granularity == "auto" and len({item["granularity"] for item in exact_matches}) > 1:
        return _not_found(
            target_module,
            available_modules,
            f"Target module '{target_module}' matches multiple granularities; specify target_granularity.",
            target_granularity,
        )
    if not exact_matches:
        return _not_found(target_module, available_modules, None, target_granularity)

    module = dict(exact_matches[0])

    return {
        "found": True,
        "module": module,
        "available_modules": available_modules,
        "parent_arch_id": source.get("source_id", "ARCH-PACKAGE"),
        "source_files": catalog.get("source_files", []),
        "target_granularity": module["granularity"],
        "architecture_coverage_gaps": _unique_text(
            catalog.get("architecture_coverage_gaps", [])
            + module.get("interface_coverage_gaps", [])
            + module.get("event_coverage_gaps", [])
            + module.get("metric_coverage_gaps", [])
        ),
    }


def _build_markdown_catalog(source: dict[str, Any], target_granularity: str) -> dict[str, Any]:
    files = source.get("files", {})
    deployable_modules = _parse_deployable_modules(files.get("02-module-partitioning.md", ""))
    bounded_contexts = _parse_bounded_contexts(files)
    components = _parse_components(files.get("02-module-partitioning.md", ""))
    all_units = deployable_modules + bounded_contexts + components
    available_modules = _unique([item["name"] for item in all_units])

    if target_granularity == "auto":
        selected_units = all_units
    else:
        selected_units = [unit for unit in all_units if unit.get("granularity") == target_granularity]

    contract_content = files.get("06-interface-contracts.md", "")
    interfaces = _extract_all_interfaces(contract_content)
    events = _extract_event_contracts(contract_content)
    metric_contracts = _extract_metric_contracts(contract_content)
    data_assets = _extract_data_assets(files.get("05-data-model.md", ""), all_units)
    all_names = _unique(available_modules + EXTERNAL_NAMES)
    enriched_units: list[dict[str, Any]] = []
    data_owners: dict[str, set[str]] = {}

    for asset in data_assets:
        scores = {
            unit["name"]: _data_asset_owner_score(unit, asset)
            for unit in selected_units
        }
        best_score = max(scores.values(), default=0)
        data_owners[asset["key"]] = {
            name for name, score in scores.items() if best_score > 0 and score == best_score
        }

    for raw_unit in selected_units:
        unit = dict(raw_unit)
        aliases = _module_aliases(unit)
        unit["interfaces"] = [
            _public_interface_for_unit(interface, unit)
            for interface in interfaces
            if interface.get("complete") and _interface_belongs_to_unit(interface, unit)
        ]
        unit["events"] = [
            _public_event(event)
            for event in events
            if event.get("complete") and _event_belongs_to_unit(event, unit)
        ]
        unit["metric_contracts"] = [
            metric
            for metric in metric_contracts
            if metric.get("complete") and _metric_contract_belongs_to_unit(metric, unit)
        ]
        unit["data_assets"] = [
            asset
            for asset in data_assets
            if unit["name"] in data_owners.get(asset["key"], set())
        ]
        unit["dependencies"] = _extract_dependencies(files, aliases, all_names)
        unit["evidence"] = _collect_relevant_snippets(files, aliases)
        unit["source_files"] = list(files.keys())
        unit["interface_coverage_gaps"] = []
        unit["event_coverage_gaps"] = []
        unit["metric_coverage_gaps"] = []
        enriched_units.append(unit)

    gaps: list[str] = []
    for interface in interfaces:
        owning_units = [
            unit
            for unit in enriched_units
            if _interface_belongs_to_unit(interface, unit)
        ]
        if not interface.get("complete"):
            missing = ", ".join(interface.get("missing", [])) or "contract details"
            message = (
                f"Interface {interface.get('name', 'UNKNOWN')} ({interface.get('path', 'no path')}) "
                f"is incomplete in 06-interface-contracts.md: missing {missing}."
            )
            if owning_units:
                for unit in owning_units:
                    unit["interface_coverage_gaps"].append(message)
            else:
                gaps.append(message + " It also has no owner at the selected derive granularity.")
            continue
        if not owning_units:
            gaps.append(
                f"Interface {interface.get('name', 'UNKNOWN')} ({interface.get('path', 'no path')}) "
                "has no owner at the selected derive granularity."
            )

    for event in events:
        owning_units = [unit for unit in enriched_units if _event_belongs_to_unit(event, unit)]
        if not event.get("complete"):
            missing = ", ".join(event.get("missing", [])) or "event contract details"
            message = (
                f"Event {event.get('event_name', event.get('contract_id', 'UNKNOWN'))} is incomplete "
                f"in 06-interface-contracts.md: missing {missing}."
            )
            if owning_units:
                for unit in owning_units:
                    unit["event_coverage_gaps"].append(message)
            else:
                gaps.append(message + " It also has no owner at the selected derive granularity.")
            continue
        if not owning_units:
            gaps.append(
                f"Event {event.get('event_name', event.get('contract_id', 'UNKNOWN'))} "
                "has no owner at the selected derive granularity."
            )

    for metric in metric_contracts:
        owning_units = [
            unit for unit in enriched_units if _metric_contract_belongs_to_unit(metric, unit)
        ]
        if not metric.get("complete"):
            missing = ", ".join(metric.get("missing", [])) or "metric contract details"
            message = (
                f"Metric contract {metric.get('metric_id', 'UNKNOWN')} is incomplete in "
                f"06-interface-contracts.md: missing {missing}."
            )
            if owning_units:
                for unit in owning_units:
                    unit["metric_coverage_gaps"].append(message)
            else:
                gaps.append(message + " It also has no owner at the selected derive granularity.")
            continue
        if not owning_units:
            gaps.append(
                f"Metric contract {metric.get('metric_id', 'UNKNOWN')} has no owner at the selected derive granularity."
            )

    for asset in data_assets:
        if not data_owners.get(asset["key"]):
            gaps.append(
                f"Data aggregate {asset['name']} from 05-data-model.md has no owner at the selected derive granularity."
            )

    return {
        "units": enriched_units,
        "available_modules": available_modules,
        "architecture_coverage_gaps": _unique_text(gaps),
        "source_files": list(files.keys()),
    }


def _parse_deployable_modules(content: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 3 or not _has_bold(cells[0]):
            continue
        name = _clean_markdown(cells[0])
        if not _looks_like_module_name(name):
            continue
        modules.append(
            {
                "name": name,
                "granularity": "deployable_module",
                "included_contexts": _extract_possible_names(cells[1]),
                "responsibility": _clean_markdown(cells[2]),
                "partition_reason": _clean_markdown(cells[3]) if len(cells) > 3 else "",
            }
        )
    return _dedupe_modules(modules)


def _parse_bounded_contexts(files: dict[str, str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []

    overview = files.get("01-system-overview.md", "")
    for line in overview.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 2 or not _has_bold(cells[0]):
            continue
        name = _clean_markdown(cells[0])
        if not _looks_like_module_name(name):
            continue
        contexts.append(
            {
                "name": name,
                "granularity": "bounded_context",
                "responsibility": _clean_markdown(cells[1]),
            }
        )

    data_model = files.get("05-data-model.md", "")
    for heading in re.findall(r"^###\s+(.+)$", data_model, re.MULTILINE):
        name = _clean_heading_title(heading)
        if _looks_like_module_name(name):
            contexts.append(
                {
                    "name": name,
                    "granularity": "bounded_context",
                    "responsibility": _find_section_first_table_text(data_model, heading),
                }
            )

    return _dedupe_modules(contexts)


def _parse_components(content: str) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 3 or _is_table_separator(cells):
            continue
        name = _clean_markdown(cells[0])
        if name.casefold() == "component" or not name.endswith("Component"):
            continue
        components.append(
            {
                "name": name,
                "granularity": "component",
                "responsibility": _clean_markdown(cells[1]),
                "related_aggregates": _extract_possible_names(cells[2]),
            }
        )
    return _dedupe_modules(components)


def _extract_interfaces_for_target(content: str, aliases: list[str]) -> list[dict]:
    """Compatibility wrapper for callers that only have aliases."""
    return [
        _public_interface(interface)
        for interface in _extract_all_interfaces(content)
        if interface.get("complete") and _contains_any(interface.get("raw_text", ""), aliases)
    ]


def _extract_all_interfaces(content: str) -> list[dict[str, Any]]:
    """Parse both compact bullet contracts and nested API contract packages."""
    records: list[dict[str, Any]] = []
    level_two_sections = _iter_markdown_sections_at_levels(content, {2})

    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 3:
            continue
        method = _clean_markdown(cells[0]).upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            continue
        path = _clean_markdown(cells[1])
        if not path.startswith("/"):
            continue
        contract_id = _clean_markdown(cells[2])
        purpose = _clean_markdown(cells[3]) if len(cells) > 3 else contract_id
        detail_heading = ""
        detail_body = ""
        for _level, heading, body in level_two_sections:
            if contract_id and contract_id.casefold() in heading.casefold():
                detail_heading = heading
                detail_body = body
                break
        detail_block = f"{detail_heading}\n{detail_body}" if detail_heading else ""
        request_fields = _extract_contract_fields(detail_block, "input") or _extract_ts_fields(
            _extract_named_subsection(detail_body, ("Request", "请求", "输入"))
        )
        response_fields = _extract_contract_fields(detail_block, "output") or _extract_ts_fields(
            _extract_named_subsection(detail_body, ("Success Response", "Response", "成功响应", "输出"))
        )
        error_codes = _extract_error_codes(detail_block) or _extract_failure_codes(detail_block)
        if not request_fields:
            request_fields = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path)
        record = {
            "name": purpose or contract_id or path,
            "contract_id": contract_id,
            "source": "06-interface-contracts.md",
            "method": method,
            "path": path,
            "request_fields": request_fields,
            "response_fields": response_fields,
            "error_codes": error_codes,
            "raw_text": f"{purpose}\n{detail_block}",
        }
        records.append(_mark_interface_completeness(record))

    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 9:
            continue
        contract_id = _clean_markdown(cells[0])
        contract_type = _clean_markdown(cells[1]).casefold()
        if not re.fullmatch(r"(?:API|INT)-[A-Z0-9-]+", contract_id, re.IGNORECASE):
            continue
        if contract_type not in {"sync_api", "api", "http", "rest"}:
            continue
        trigger = _clean_markdown(cells[4])
        method_match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\b", trigger, re.IGNORECASE)
        path_match = re.search(r"(/\S+)", trigger)
        method = method_match.group(1).upper() if method_match else "CALL"
        path = path_match.group(1).rstrip("`.,;") if path_match else ""
        record = {
            "name": contract_id,
            "contract_id": contract_id,
            "contract_type": contract_type,
            "provider": _clean_markdown(cells[2]),
            "consumer": _clean_markdown(cells[3]),
            "source": "06-interface-contracts.md",
            "method": method,
            "path": path,
            "request_fields": _extract_table_field_list(cells[5]),
            "response_fields": _extract_table_field_list(cells[6]),
            "error_codes": [],
            "side_effects": _clean_markdown(cells[7]),
            "contract_dependencies": _clean_markdown(cells[8]),
            "raw_text": _clean_markdown(" ".join(cells)),
        }
        records.append(_mark_interface_completeness(record))

    for level, heading, body in _iter_markdown_sections_at_levels(content, {3, 4}):
        block = f"{heading}\n{body}"
        path = _extract_path(block)
        if not path:
            continue
        request_fields = _extract_contract_fields(block, "input")
        response_fields = _extract_contract_fields(block, "output")
        error_codes = _extract_error_codes(block)
        if not request_fields:
            request_fields = re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", path)
        record = {
            "name": _clean_heading_title(heading) or path,
            "source": "06-interface-contracts.md",
            "provider": _extract_contract_provider(block),
            "consumer": _extract_contract_consumer(block),
            "method": _extract_method(block),
            "path": path,
            "request_fields": request_fields,
            "response_fields": response_fields,
            "error_codes": error_codes,
            "raw_text": block,
        }
        records.append(_mark_interface_completeness(record))

    return _merge_interface_records(records)


def _mark_interface_completeness(interface: dict[str, Any]) -> dict[str, Any]:
    required_fields = ["method", "request_fields", "response_fields"]
    if interface.get("method") in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        required_fields.append("path")
    missing = [field for field in required_fields if not interface.get(field)]
    return {**interface, "complete": not missing, "missing": missing}


def _merge_interface_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        key = record.get("path") or record.get("contract_id") or _normalize_name(record.get("name", ""))
        if not key:
            continue
        if key not in by_key:
            by_key[key] = record
            order.append(key)
            continue
        current = by_key[key]
        merged = dict(current)
        for field in (
            "name",
            "contract_id",
            "method",
            "path",
            "request_fields",
            "response_fields",
            "error_codes",
            "provider",
            "consumer",
            "side_effects",
            "contract_dependencies",
        ):
            if not merged.get(field) and record.get(field):
                merged[field] = record[field]
        merged["raw_text"] = "\n".join(
            part for part in (current.get("raw_text", ""), record.get("raw_text", "")) if part
        )
        by_key[key] = _mark_interface_completeness(merged)
    return [by_key[key] for key in order]


def _public_interface(interface: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in interface.items()
        if key not in {"raw_text", "complete", "missing"}
    }


def _public_interface_for_unit(
    interface: dict[str, Any],
    unit: dict[str, Any],
) -> dict[str, Any]:
    public = _public_interface(interface)
    aliases = _module_aliases(unit)
    provider_match = _contains_any(interface.get("provider", ""), aliases)
    consumer_match = _contains_any(interface.get("consumer", ""), aliases)
    if provider_match and consumer_match:
        public["ownership_role"] = "provider_and_consumer"
    elif consumer_match:
        public["ownership_role"] = "consumer"
    else:
        public["ownership_role"] = "provider"
    return public


def _extract_named_subsection(content: str, names: tuple[str, ...]) -> str:
    name_pattern = "|".join(re.escape(name) for name in names)
    match = re.search(rf"^###\s+(?:{name_pattern})(?:\s*\([^)]*\))?\s*$", content, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    next_heading = re.search(r"^###\s+", content[match.end():], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(content)
    return content[match.end():end]


def _extract_ts_fields(content: str) -> list[str]:
    fields = re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", content, re.MULTILINE)
    fields.extend(
        re.findall(r"(?:[\{;,]\s*)([A-Za-z_][A-Za-z0-9_]*)\??\s*:", content)
    )
    return _unique(fields)


def _extract_table_field_list(cell: str) -> list[str]:
    fields = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", cell)
    if not fields:
        fields = [
            part.strip()
            for part in re.split(r"[,、]", _clean_markdown(cell))
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part.strip())
        ]
    return _unique(fields)


def _extract_failure_codes(content: str) -> list[str]:
    code_match = re.search(r"\bcode\s*:\s*(.*?);", content, re.DOTALL | re.IGNORECASE)
    codes = re.findall(r'["\']([A-Za-z0-9_-]+)["\']', code_match.group(1)) if code_match else []
    status_codes = re.findall(r"Failure Response\s*\((\d{3})\)", content, re.IGNORECASE)
    return _unique(codes + status_codes)


def _extract_contract_provider(content: str) -> str:
    match = re.search(
        r"(?:接口所有者|Provider|Owner)\s*\*{0,2}\s*[：:]\s*([^\n]+)",
        content,
        re.IGNORECASE,
    )
    return _clean_markdown(match.group(1)) if match else ""


def _extract_contract_consumer(content: str) -> str:
    match = re.search(
        r"Consumer\s*\*{0,2}\s*[：:]\s*([^\n]+)",
        content,
        re.IGNORECASE,
    )
    return _clean_markdown(match.group(1)) if match else ""


def _interface_belongs_to_unit(interface: dict[str, Any], unit: dict[str, Any]) -> bool:
    raw_text = interface.get("raw_text", "")
    aliases = _module_aliases(unit)
    provider = interface.get("provider", "")
    consumer = interface.get("consumer", "")
    if provider or consumer:
        return _contains_any(provider, aliases) or _contains_any(consumer, aliases)
    if _contains_any(raw_text, aliases):
        return True
    unit_text = " ".join(
        [unit.get("name", ""), unit.get("responsibility", "")]
        + unit.get("included_contexts", [])
        + unit.get("related_aggregates", [])
    )
    interface_text = " ".join(
        [
            interface.get("name", ""),
            interface.get("contract_id", ""),
            raw_text,
        ]
    )
    score = _semantic_overlap_score(unit_text, interface_text)
    if score >= 4:
        return True
    unit_name_tokens = _semantic_tokens(unit.get("name", ""))
    interface_tokens = _semantic_tokens(interface_text)
    return score >= 2 and bool(unit_name_tokens & interface_tokens)


def _extract_event_contracts(content: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 9:
            continue
        contract_id = _clean_markdown(cells[0])
        contract_type = _clean_markdown(cells[1]).casefold()
        if not re.fullmatch(r"EVT-[A-Z0-9-]+", contract_id, re.IGNORECASE):
            continue
        if contract_type != "event":
            continue
        event = {
            "contract_id": contract_id,
            "contract_type": contract_type,
            "event_name": _clean_markdown(cells[2]),
            "publisher": _clean_markdown(cells[3]),
            "consumers": _clean_markdown(cells[4]),
            "required_fields": _extract_table_field_list(cells[5]),
            "produced_fields": _extract_table_field_list(cells[6]),
            "side_effects": _clean_markdown(cells[7]),
            "contract_dependencies": _clean_markdown(cells[8]),
            "source": "06-interface-contracts.md",
            "raw_text": _clean_markdown(" ".join(cells)),
        }
        required = ("contract_id", "event_name", "publisher", "required_fields", "produced_fields")
        missing = [field for field in required if not event.get(field)]
        event["complete"] = not missing
        event["missing"] = missing
        events.append(event)
    return events


def _event_belongs_to_unit(event: dict[str, Any], unit: dict[str, Any]) -> bool:
    aliases = _module_aliases(unit)
    return _contains_any(event.get("publisher", ""), aliases) or _contains_any(
        event.get("consumers", ""),
        aliases,
    )


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in {"raw_text", "complete", "missing"}
    }


def _extract_metric_contracts(content: str) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 8:
            continue
        metric_id = _clean_markdown(cells[0])
        if not re.fullmatch(r"MET-[A-Z0-9-]+", metric_id, re.IGNORECASE):
            continue
        metric = {
            "metric_id": metric_id,
            "owner": _clean_markdown(cells[1]),
            "source_evidence": _clean_markdown(cells[2]),
            "start": _clean_markdown(cells[3]),
            "end": _clean_markdown(cells[4]),
            "threshold": _clean_markdown(cells[5]),
            "exclusions": _clean_markdown(cells[6]),
            "evidence": _clean_markdown(cells[7]),
            "source": "06-interface-contracts.md",
        }
        required = ("metric_id", "owner", "source_evidence", "start", "end", "threshold", "evidence")
        missing = [field for field in required if not metric.get(field)]
        metric["complete"] = not missing
        metric["missing"] = missing
        metrics.append(metric)
    return metrics


def _metric_contract_belongs_to_unit(metric: dict[str, Any], unit: dict[str, Any]) -> bool:
    owner = metric.get("owner", "")
    aliases = _module_aliases(unit)
    if _contains_any(owner, aliases):
        return True
    unit_text = " ".join([unit.get("name", "")] + unit.get("included_contexts", []))
    return _semantic_overlap_score(owner, unit_text) >= 2


def _extract_data_assets(content: str, units: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract aggregate roots that require an owned persistence/migration path."""
    assets: list[dict[str, str]] = []
    current_h2 = ""
    current_h3 = ""
    unit_names = [unit.get("name", "") for unit in units]
    unit_aliases = _unique(
        unit_names
        + [alias for unit in units for alias in unit.get("included_contexts", [])]
    )
    aggregate_labels = {"聚合根", "aggregate root", "aggregate roots"}
    header_labels = {
        "聚合根",
        "aggregate root",
        "aggregate",
        "对象",
        "entity",
        "field",
    }

    for line in content.splitlines():
        h2 = re.match(r"^##\s+(.+)$", line.strip())
        if h2:
            current_h2 = _clean_heading_title(h2.group(1))
            current_h3 = ""
            continue
        h3 = re.match(r"^###\s+(.+)$", line.strip())
        if h3:
            current_h3 = _clean_heading_title(h3.group(1))
            continue

        cells = _split_markdown_row(line)
        if len(cells) < 2:
            continue
        name = _clean_markdown(cells[0])
        if name.casefold() in header_labels:
            continue

        h2_label = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", current_h2).casefold()
        h3_label = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", current_h3).casefold()
        in_aggregate_table = h2_label in aggregate_labels or h3_label in aggregate_labels
        context_heading = current_h2 if h3_label in aggregate_labels else current_h3
        if not in_aggregate_table and context_heading:
            in_aggregate_table = any(_same_name(context_heading, alias) for alias in unit_aliases)
        if not in_aggregate_table or not _looks_like_data_name(name):
            continue

        context = current_h2 if h3_label in aggregate_labels else context_heading
        asset = {
            "name": name,
            "context": context,
            "description": _clean_markdown(" ".join(cells[1:])),
            "source": "05-data-model.md",
            "key": f"{_normalize_name(context)}:{_normalize_name(name)}",
        }
        assets.append(asset)

    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for asset in assets:
        if asset["key"] in seen:
            continue
        seen.add(asset["key"])
        result.append(asset)
    return result


def _looks_like_data_name(name: str) -> bool:
    if not name or len(name) > 80 or " " in name.strip():
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{2,}", name))


def _data_asset_owner_score(unit: dict[str, Any], asset: dict[str, str]) -> int:
    aliases = _module_aliases(unit)
    context = asset.get("context", "")
    if context and any(_same_name(context, alias) or _contains_any(context, [alias]) for alias in aliases):
        return 100

    asset_name = asset.get("name", "")
    if any(_same_name(asset_name, related) for related in unit.get("related_aggregates", [])):
        return 95

    unit_base = re.sub(
        r"(?:module|component|context|service|center|gateway|bc)$",
        "",
        _normalize_name(unit.get("name", "")),
    )
    asset_normalized = _normalize_name(asset_name)
    if unit_base and len(unit_base) >= 5 and (
        unit_base in asset_normalized or asset_normalized in unit_base
    ):
        return 85

    unit_text = " ".join(
        [unit.get("name", ""), unit.get("responsibility", "")]
        + unit.get("related_aggregates", [])
    )
    asset_text = " ".join(
        [asset_name, asset.get("context", ""), asset.get("description", "")]
    )
    overlap = _semantic_overlap_score(unit_text, asset_text)
    return 40 + overlap if overlap >= 2 else 0


def _semantic_overlap_score(left: str, right: str) -> int:
    left_tokens = _semantic_tokens(left)
    right_tokens = _semantic_tokens(right)
    return len(left_tokens & right_tokens)


def _semantic_tokens(text: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    expanded = expanded.replace("_", " ").replace("-", " ")
    latin = {
        token.casefold().rstrip("s")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", expanded)
        if len(token) >= 3 and token.casefold() not in {"module", "component", "service", "system"}
    }
    cjk_tokens: set[str] = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3, 4):
            for index in range(len(chunk) - size + 1):
                cjk_tokens.add(chunk[index:index + size])
    lowered = text.casefold()
    concepts: set[str] = set()
    concept_markers = {
        "upload": ("upload", "submission", "submit", "上传", "提交"),
        "validation": ("validation", "validate", "invalid", "校验", "验证"),
        "consent": ("consent", "privacy", "隐私", "同意"),
        "recognition": ("recognition", "recognize", "识别"),
        "session": ("session", "会话"),
    }
    for concept, markers in concept_markers.items():
        if any(marker in lowered for marker in markers):
            concepts.add(concept)
    return latin | cjk_tokens | concepts


def _extract_path(text: str) -> str:
    match = re.search(r"`\s*(?:GET|POST|PUT|PATCH|DELETE)\s+([^`]+)`", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_contract_fields(text: str, field_type: str) -> list[str]:
    if field_type == "input":
        labels = ("输入", "请求", "required_fields")
        stop_labels = ("输出", "响应", "错误", "produced_fields")
    else:
        labels = ("输出", "响应", "produced_fields")
        stop_labels = ("错误", "error_codes", "幂等", "性能")

    section = _extract_labeled_section(text, labels, stop_labels)
    fields = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", section)
    fields.extend(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', section))
    fields = [field for field in fields if field.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "JSON"}]
    return _unique(fields)


def _extract_error_codes(text: str) -> list[str]:
    section = _extract_labeled_section(
        text,
        ("错误码", "error_codes"),
        ("幂等", "性能", "超时", "ACL"),
    )
    codes = re.findall(r"`(\d{3}|[A-Z][A-Z0-9_]+)`", section)
    return _unique([code for code in codes if code.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "JSON"}])


def _extract_labeled_section(text: str, labels: tuple[str, ...], stop_labels: tuple[str, ...]) -> str:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(label_pattern, text, re.IGNORECASE)
    if not match:
        return ""

    section = text[match.end():]
    stop_pattern = "|".join(re.escape(label) for label in stop_labels)
    stop = re.search(rf"\n\s*-\s*\*\*(?:{stop_pattern})", section, re.IGNORECASE)
    if stop:
        section = section[: stop.start()]
    return section


def _extract_dependencies(files: dict[str, str], aliases: list[str], all_names: list[str]) -> list[dict]:
    dependencies: list[dict] = []
    target_names = {_normalize_name(alias) for alias in aliases}
    for filename, content in files.items():
        for _level, heading, body in _iter_markdown_sections(content):
            block = f"{heading}\n{body}"
            ownership_lines = [
                line
                for line in body.splitlines()
                if re.search(r"(?:Provider|Consumer|Owner|调用方|接口所有者)", line, re.IGNORECASE)
                and _contains_any(line, aliases)
            ]
            if not _contains_any(heading, aliases) and not ownership_lines:
                continue
            for name in all_names:
                if _normalize_name(name) in target_names:
                    continue
                if _contains_any(block, [name]):
                    dependencies.append(
                        {
                            "name": name,
                            "source": filename,
                            "evidence": _clean_markdown(heading),
                            "relationship": "owner_or_caller",
                        }
                    )
        for line in content.splitlines():
            if not _contains_any(line, aliases):
                continue
            relationship = "related"
            cells = _split_markdown_row(line)
            if len(cells) >= 4:
                provider = _clean_markdown(cells[2])
                consumer = _clean_markdown(cells[3])
                if _contains_any(provider, aliases):
                    relationship = "provider"
                elif _contains_any(consumer, aliases):
                    relationship = "consumer"
            for name in all_names:
                if _normalize_name(name) in target_names:
                    continue
                if _contains_any(line, [name]):
                    dependencies.append(
                        {
                            "name": name,
                            "source": filename,
                            "evidence": _clean_markdown(line).strip(),
                            "relationship": relationship,
                        }
                    )
    return _dedupe_dicts_by_name(dependencies)


def _collect_relevant_snippets(files: dict[str, str], aliases: list[str], limit: int = 40) -> list[dict]:
    snippets: list[dict] = []
    for filename, content in files.items():
        for line_no, line in enumerate(content.splitlines(), start=1):
            if _contains_any(line, aliases):
                snippets.append(
                    {
                        "source": filename,
                        "line": line_no,
                        "text": _clean_markdown(line).strip(),
                    }
                )
                if len(snippets) >= limit:
                    return snippets
    return snippets


def _iter_markdown_sections(content: str) -> list[tuple[int, str, str]]:
    return _iter_markdown_sections_at_levels(content, {3, 4})


def _iter_markdown_sections_at_levels(
    content: str,
    levels: set[int],
) -> list[tuple[int, str, str]]:
    matches = [
        match
        for match in re.finditer(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        if len(match.group(1)) in levels
    ]
    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append((len(match.group(1)), match.group(2).strip(), content[start:end]))
    return sections


def _find_section_first_table_text(content: str, heading: str) -> str:
    pattern = re.compile(rf"^###\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return ""
    next_heading = re.search(r"^###\s+", content[match.end():], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(content)
    section = content[match.end():end]
    for line in section.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) >= 2 and not _is_table_separator(cells):
            return _clean_markdown(" ".join(cells))
    return ""


def _module_aliases(module: dict[str, Any]) -> list[str]:
    aliases = [module["name"]]
    aliases.extend(module.get("included_contexts", []))
    return [alias for alias in _unique(aliases) if alias]


def _extract_method(text: str) -> str:
    path_method = re.search(r"`\s*(GET|POST|PUT|PATCH|DELETE)\s+[^`]+`", text, re.IGNORECASE)
    if path_method:
        return path_method.group(1).upper()
    method_match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE|gRPC|WebSocket|HTTPS|event)\b", text, re.IGNORECASE)
    return method_match.group(1).upper() if method_match else ""


def _not_found(
    target_module: str,
    available_modules: list[str],
    error: str | None,
    target_granularity: str,
) -> dict:
    return {
        "found": False,
        "module": None,
        "available_modules": available_modules,
        "parent_arch_id": "UNKNOWN",
        "source_files": [],
        "target_granularity": target_granularity,
        "error": error or f"Module '{target_module}' was not found in the architecture input (不存在).",
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _try_load_yaml(content: str) -> Any:
    try:
        return yaml.safe_load(content)
    except Exception:
        return None


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if _is_table_separator(cells):
        return []
    return cells


def _is_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells if cell.strip())


def _has_bold(text: str) -> bool:
    return "**" in text


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_heading_title(text: str) -> str:
    text = _clean_markdown(text)
    text = re.sub(r"^\d+(?:\.\d+)*\s+", "", text)
    text = re.sub(r"^[\d.]+\s*", "", text)
    return text.strip(" -")


def _extract_possible_names(text: str) -> list[str]:
    cleaned = _clean_markdown(text)
    parts = re.split(r"[,/;+]| and |、|，|；", cleaned)
    return [part.strip() for part in parts if _looks_like_module_name(part.strip())]


def _looks_like_module_name(name: str) -> bool:
    if not name or len(name) > 80:
        return False
    lowered = name.lower()
    if lowered in {"module", "bc", "bounded context", "source", "target", "component"}:
        return False
    return any(
        marker in name
        for marker in (
            "Core",
            "Agent",
            "Center",
            "Gateway",
            "Service",
            "Module",
            "Context",
            " BC",
            "PC ",
        )
    )


def _same_name(left: str, right: str) -> bool:
    return _normalize_name(left) == _normalize_name(right)


def _normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _contains_any(text: str, aliases: list[str]) -> bool:
    normalized_text = _normalize_name(text)
    return any(alias and _normalize_name(alias) in normalized_text for alias in aliases)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if not item:
            continue
        key = _normalize_name(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _unique_text(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for module in modules:
        key = (module.get("granularity"), _normalize_name(module.get("name", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(module)
    return result


def _dedupe_dicts_by_name(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        raw_name = str(item.get("name", ""))
        key = _normalize_name(raw_name) or raw_name.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
