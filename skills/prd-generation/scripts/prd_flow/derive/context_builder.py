"""Build derive mode context from parent PRD and architecture package."""
from __future__ import annotations

import re
from pathlib import Path

from prd_flow.derive.parser import (
    extract_architecture_catalog,
    extract_module_context,
    parse_parent_prd,
)


def build_derive_context(
    parent_prd_path: Path,
    architecture_package_path: Path,
    target_module: str,
    target_granularity: str = "auto",
) -> dict:
    """Build complete context for Derive mode."""
    parent_prd = parse_parent_prd(parent_prd_path)
    parent_doc_id = parent_prd.get("doc_id", "UNKNOWN")

    arch_result = extract_module_context(
        architecture_package_path,
        target_module,
        target_granularity=target_granularity,
    )

    if not arch_result["found"]:
        return {
            "success": False,
            "parent_doc_id": parent_doc_id,
            "parent_arch_id": arch_result.get("parent_arch_id", "UNKNOWN"),
            "module_name": target_module,
            "module": None,
            "related_requirements": [],
            "related_architecture_requirements": [],
            "related_non_functional": [],
            "related_success_metrics": [],
            "non_goals": [],
            "related_scenarios": [],
            "interfaces": [],
            "events": [],
            "metric_contracts": [],
            "dependencies": [],
            "external_dependencies": [],
            "data_assets": [],
            "implementation_surfaces": [],
            "requirement_surfaces": {},
            "interface_parent_refs": {},
            "data_parent_refs": [],
            "artifact_parent_refs": {},
            "orphan_requirements": [],
            "uncovered_architecture_requirements": [],
            "coverage_gaps": [],
            "derive_warnings": [],
            "coverage_ledger": [],
            "coverage_complete": False,
            "error": arch_result.get("error") or f"Module '{target_module}' was not found in the architecture input.",
            "available_modules": arch_result.get("available_modules", []),
            "target_granularity": arch_result.get("target_granularity", target_granularity),
            "source_files": arch_result.get("source_files", []),
        }

    module = arch_result["module"]
    module_name = module.get("name", target_module)

    resolved_granularity = module.get("granularity", arch_result.get("target_granularity", target_granularity))
    catalog = extract_architecture_catalog(architecture_package_path, resolved_granularity)
    units = catalog.get("units", []) or [module]
    target_owner = _owner_name(module_name, units)
    catalog_module = next(
        (unit for unit in units if _normalize_keyword(unit.get("name", "")) == _normalize_keyword(module_name)),
        module,
    )
    interfaces = catalog_module.get("interfaces", []) if isinstance(catalog_module, dict) else []
    events = catalog_module.get("events", []) if isinstance(catalog_module, dict) else []
    metric_contracts = catalog_module.get("metric_contracts", []) if isinstance(catalog_module, dict) else []
    dependencies = catalog_module.get("dependencies", []) if isinstance(catalog_module, dict) else []
    external_dependencies = _external_dependencies(dependencies)
    data_assets = catalog_module.get("data_assets", []) if isinstance(catalog_module, dict) else []

    all_requirements = parent_prd.get("requirements", [])
    parent_architecture_requirements = [
        req
        for req in all_requirements
        if str(req.get("source_kind", "")).startswith("architecture_")
    ]
    business_requirements = [
        req for req in all_requirements if req not in parent_architecture_requirements
    ]
    all_non_functional = parent_prd.get("non_functional", [])
    all_success_metrics = [
        metric
        for metric in parent_prd.get("success_metrics", [])
        if not _is_derive_control_metric(metric)
    ]
    non_goals = parent_prd.get("non_goals", [])
    acceptance_scenarios = parent_prd.get("acceptance_scenarios", [])
    requirement_owners = _build_ownership_map(
        business_requirements + all_non_functional,
        units,
        acceptance_scenarios,
    )
    (
        architecture_owners,
        interface_parent_refs,
        data_parent_refs,
        artifact_parent_refs,
        architecture_parent_gaps,
    ) = _map_parent_architecture_requirements(parent_architecture_requirements, units)
    requirement_owners.update(architecture_owners)
    _propagate_frontend_business_ownership(
        business_requirements,
        parent_architecture_requirements,
        architecture_owners,
        requirement_owners,
        architecture_parent_gaps,
    )
    _propagate_scenario_co_ownership(requirement_owners, acceptance_scenarios)

    unit_names = {unit.get("name", "") for unit in units if unit.get("name")}
    metric_items = [
        {
            "id": metric.get("id") or f"METRIC-{index:03d}",
            "text": f"{metric.get('name', '')} {metric.get('method', '')}",
        }
        for index, metric in enumerate(all_success_metrics, start=1)
    ]
    metric_owners = _map_success_metric_owners(all_success_metrics, metric_items, units)
    for metric_item in metric_items:
        if not metric_owners.get(metric_item["id"]):
            metric_owners[metric_item["id"]] = set(unit_names)
    related_success_metrics = [
        metric
        for metric, metric_item in zip(all_success_metrics, metric_items)
        if target_owner in metric_owners.get(metric_item["id"], set())
    ]
    ignored_control_nfrs = [nfr for nfr in all_non_functional if _is_derive_control_nfr(nfr)]
    for nfr in all_non_functional:
        if _is_derive_control_nfr(nfr):
            continue
        if not requirement_owners.get(nfr.get("id", "")):
            requirement_owners[nfr.get("id", "")] = set(unit_names)

    related_requirements = [
        req
        for req in business_requirements
        if target_owner in requirement_owners.get(req.get("id", ""), set())
    ]
    related_architecture_requirements = [
        req
        for req in parent_architecture_requirements
        if target_owner in requirement_owners.get(req.get("id", ""), set())
    ]
    related_non_functional = []
    for nfr in all_non_functional:
        if target_owner not in requirement_owners.get(nfr.get("id", ""), set()):
            continue
        inherited = dict(nfr)
        if requirement_owners.get(nfr.get("id", ""), set()) == unit_names:
            inherited["inherited_globally"] = True
        related_non_functional.append(inherited)

    orphan_requirements = [
        req
        for req in business_requirements
        if not requirement_owners.get(req.get("id", ""))
    ]
    uncovered_architecture_requirements = [
        req
        for req in parent_architecture_requirements
        if not requirement_owners.get(req.get("id", ""))
    ]
    known_ids = {
        item.get("id", "")
        for item in all_requirements + all_non_functional
        if item.get("id")
    }
    untraced_scenarios = [
        scenario
        for scenario in acceptance_scenarios
        if not scenario.get("requirement_ids")
    ]
    unknown_scenario_refs = sorted(
        {
            req_id
            for scenario in acceptance_scenarios
            for req_id in scenario.get("requirement_ids", [])
            if req_id not in known_ids
        }
    )
    related_ids = {
        item.get("id", "")
        for item in related_requirements + related_architecture_requirements + related_non_functional
    }
    related_scenarios = [
        scenario
        for scenario in acceptance_scenarios
        if related_ids.intersection(scenario.get("requirement_ids", []))
    ]

    coverage_gaps = list(catalog.get("architecture_coverage_gaps", []))
    coverage_gaps.extend(architecture_parent_gaps)
    coverage_gaps.extend(
        f"Parent requirement {req.get('id', 'UNKNOWN')} has no owner at granularity {resolved_granularity}."
        for req in orphan_requirements
    )
    coverage_gaps.extend(
        f"Acceptance scenario '{scenario.get('scenario', 'UNKNOWN')}' has no requirement tag."
        for scenario in untraced_scenarios
    )
    coverage_gaps.extend(
        f"Acceptance scenario references unknown requirement {req_id}."
        for req_id in unknown_scenario_refs
    )

    coverage_gaps.extend(catalog_module.get("interface_coverage_gaps", []))
    coverage_gaps.extend(catalog_module.get("event_coverage_gaps", []))
    coverage_gaps.extend(catalog_module.get("metric_coverage_gaps", []))
    coverage_gaps = list(dict.fromkeys(coverage_gaps))
    coverage_ledger = _build_coverage_ledger(
        business_requirements=business_requirements,
        architecture_requirements=parent_architecture_requirements,
        non_functional=all_non_functional,
        requirement_owners=requirement_owners,
        target_owner=target_owner,
        ignored_ids={item.get("id", "") for item in ignored_control_nfrs},
    )
    requirement_surfaces = {
        req.get("id", ""): _detect_implementation_surfaces(
            req.get("text", ""),
            [
                scenario
                for scenario in related_scenarios
                if req.get("id", "") in scenario.get("requirement_ids", [])
            ],
        )
        for req in related_requirements
    }
    implementation_surfaces = _module_implementation_surfaces(
        catalog_module,
        related_requirements,
        related_scenarios,
        interfaces,
        dependencies,
        data_assets,
    )
    if (
        related_success_metrics
        or any(_nfr_requires_observability(nfr) for nfr in related_non_functional)
    ) and "observability" not in implementation_surfaces:
        implementation_surfaces.append("observability")
    if any(
        filename in {"03-runtime-architecture.md", "08-deployment.md"}
        for filename in catalog.get("source_files", [])
    ) and "integration_wiring" not in implementation_surfaces:
        implementation_surfaces.append("integration_wiring")

    return {
        "success": True,
        "parent_doc_id": parent_doc_id,
        "parent_arch_id": arch_result.get("parent_arch_id", "UNKNOWN"),
        "module_name": module_name,
        "module": catalog_module,
        "related_requirements": related_requirements,
        "related_architecture_requirements": related_architecture_requirements,
        "related_non_functional": related_non_functional,
        "related_success_metrics": related_success_metrics,
        "non_goals": non_goals,
        "related_scenarios": related_scenarios,
        "orphan_requirements": orphan_requirements,
        "uncovered_architecture_requirements": uncovered_architecture_requirements,
        "untraced_scenarios": untraced_scenarios,
        "unknown_scenario_refs": unknown_scenario_refs,
        "ignored_control_nfrs": ignored_control_nfrs,
        "coverage_gaps": coverage_gaps,
        "derive_warnings": coverage_gaps,
        "coverage_ledger": coverage_ledger,
        "coverage_complete": all(
            item["status"] != "unassigned" for item in coverage_ledger
        ),
        "requirement_owners": {
            req_id: sorted(owners)
            for req_id, owners in requirement_owners.items()
        },
        "requirement_surfaces": requirement_surfaces,
        "interface_parent_refs": interface_parent_refs,
        "data_parent_refs": data_parent_refs.get(target_owner, []),
        "artifact_parent_refs": artifact_parent_refs,
        "implementation_surfaces": implementation_surfaces,
        "data_assets": data_assets,
        "interfaces": interfaces if isinstance(interfaces, list) else [],
        "events": events if isinstance(events, list) else [],
        "metric_contracts": metric_contracts if isinstance(metric_contracts, list) else [],
        "dependencies": dependencies if isinstance(dependencies, list) else [],
        "external_dependencies": external_dependencies,
        "error": None,
        "available_modules": arch_result.get("available_modules", []),
        "target_granularity": resolved_granularity,
        "source_files": arch_result.get("source_files", []),
    }


def _owner_name(module_name: str, units: list[dict]) -> str:
    normalized = _normalize_keyword(module_name)
    for unit in units:
        name = unit.get("name", "")
        if _normalize_keyword(name) == normalized:
            return name
    return module_name


def _build_coverage_ledger(
    business_requirements: list[dict],
    architecture_requirements: list[dict],
    non_functional: list[dict],
    requirement_owners: dict[str, set[str]],
    target_owner: str,
    ignored_ids: set[str],
) -> list[dict]:
    """Describe where every parent obligation is expected to be inherited."""
    ledger: list[dict] = []
    typed_items = (
        [("requirement", item) for item in business_requirements]
        + [("architecture_requirement", item) for item in architecture_requirements]
        + [("non_functional", item) for item in non_functional]
    )
    for kind, item in typed_items:
        item_id = item.get("id", "")
        if not item_id or item_id in ignored_ids:
            continue
        owners = sorted(requirement_owners.get(item_id, set()))
        if target_owner in owners:
            status = "inherited_by_target"
        elif owners:
            status = "assigned_to_other_targets"
        else:
            status = "unassigned"
        ledger.append(
            {
                "id": item_id,
                "kind": kind,
                "priority": item.get("priority"),
                "owners": owners,
                "status": status,
            }
        )
    return ledger


def _build_ownership_map(
    requirements: list[dict],
    units: list[dict],
    scenarios: list[dict],
) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for req in requirements:
        req_id = req.get("id", "")
        linked_scenarios = [
            scenario
            for scenario in scenarios
            if req_id in scenario.get("requirement_ids", [])
        ]
        owners[req_id] = {
            unit.get("name", "")
            for unit in units
            if unit.get("name") and _requirement_matches_unit(req, unit, linked_scenarios)
        }
    return owners


def _map_success_metric_owners(
    metrics: list[dict],
    metric_items: list[dict],
    units: list[dict],
) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for metric, metric_item in zip(metrics, metric_items):
        metric_text = " ".join(
            [metric.get("name", ""), metric.get("target", ""), metric.get("method", "")]
        )
        metric_numbers = set(re.findall(r"\d+(?:\.\d+)?", metric_text))
        candidates: list[tuple[int, str]] = []
        for unit in units:
            for contract in unit.get("metric_contracts", []):
                contract_text = " ".join(
                    str(contract.get(field, ""))
                    for field in (
                        "metric_id",
                        "source_evidence",
                        "start",
                        "end",
                        "threshold",
                        "exclusions",
                        "evidence",
                    )
                )
                score = len(
                    _generic_semantic_tokens(metric_text)
                    & _generic_semantic_tokens(contract_text)
                )
                contract_numbers = set(re.findall(r"\d+(?:\.\d+)?", contract_text))
                score += 5 * len(metric_numbers & contract_numbers)
                if score > 0:
                    candidates.append((score, unit.get("name", "")))
        if candidates:
            best_score = max(score for score, _unit_name in candidates)
            owners[metric_item["id"]] = {
                unit_name
                for score, unit_name in candidates
                if score == best_score and unit_name
            }
        else:
            owners[metric_item["id"]] = set()
    return owners


def _map_parent_architecture_requirements(
    requirements: list[dict],
    units: list[dict],
) -> tuple[
    dict[str, set[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    list[str],
]:
    owners: dict[str, set[str]] = {}
    interface_parent_refs: dict[str, list[str]] = {}
    data_parent_refs: dict[str, list[str]] = {}
    artifact_parent_refs: dict[str, list[str]] = {}
    gaps: list[str] = []

    for req in requirements:
        req_id = req.get("id", "")
        source_kind = req.get("source_kind", "")
        text = req.get("text", "")
        owners[req_id] = set()

        if source_kind == "architecture_frontend":
            for unit in units:
                if not _unit_has_explicit_frontend_owner(unit):
                    continue
                unit_name = unit.get("name", "")
                owners[req_id].add(unit_name)
            if owners[req_id]:
                artifact_parent_refs.setdefault("frontend", []).append(req_id)
            else:
                gaps.append(
                    f"Parent architecture frontend obligation {req_id} has no child owner that explicitly "
                    "declares a frontend, Web App, browser, page, UI, or client responsibility."
                )
            continue

        if source_kind == "architecture_interface":
            operation = re.search(
                r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s）：；]+)",
                text,
                re.IGNORECASE,
            )
            parent_method = operation.group(1).upper() if operation else ""
            parent_path = operation.group(2).rstrip("。.,;") if operation else ""
            parent_anchor = str(req.get("parent_req", "")).split("#", 1)[-1]
            for unit in units:
                for interface in unit.get("interfaces", []):
                    current_id = str(
                        interface.get("contract_id")
                        or interface.get("name")
                        or interface.get("path")
                    )
                    same_http_operation = (
                        parent_path
                        and interface.get("path") == parent_path
                        and (not parent_method or interface.get("method") == parent_method)
                    )
                    same_contract = parent_anchor and parent_anchor in {
                        str(interface.get("contract_id", "")),
                        str(interface.get("name", "")),
                    }
                    if not same_http_operation and not same_contract:
                        continue
                    owners[req_id].add(unit.get("name", ""))
                    interface_parent_refs.setdefault(current_id, [])
                    if req_id not in interface_parent_refs[current_id]:
                        interface_parent_refs[current_id].append(req_id)
            if not owners[req_id]:
                operation_label = f"{parent_method} {parent_path}".strip() or parent_anchor or req_id
                gaps.append(
                    f"Parent architecture interface {req_id} ({operation_label}) is not represented "
                    "in the child architecture catalog."
                )
            continue

        if source_kind == "architecture_data":
            for unit in units:
                if not unit.get("data_assets"):
                    continue
                unit_name = unit.get("name", "")
                owners[req_id].add(unit_name)
                data_parent_refs.setdefault(unit_name, []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture data obligation {req_id} has no child data owner."
                )
            continue

        if source_kind == "architecture_event":
            event_match = re.search(r"事件\s+([^\s：:；]+)", text)
            parent_event = event_match.group(1) if event_match else ""
            for unit in units:
                for event in unit.get("events", []):
                    if parent_event and event.get("event_name") != parent_event:
                        continue
                    unit_name = unit.get("name", "")
                    owners[req_id].add(unit_name)
                    artifact_key = f"event:{event.get('contract_id') or event.get('event_name')}"
                    artifact_parent_refs.setdefault(artifact_key, []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture event {req_id} ({parent_event or 'unknown event'}) has no child owner."
                )
            continue

        if source_kind == "architecture_adapter":
            adapter_match = re.search(r"适配器\s+([^（：:，,；。]+)", text)
            parent_adapter = adapter_match.group(1).strip() if adapter_match else ""
            for unit in units:
                for dependency in _external_dependencies(unit.get("dependencies", [])):
                    dependency_name = str(dependency.get("name", ""))
                    if parent_adapter and _normalize_keyword(parent_adapter) != _normalize_keyword(dependency_name):
                        continue
                    unit_name = unit.get("name", "")
                    owners[req_id].add(unit_name)
                    artifact_key = f"adapter:{_normalize_keyword(dependency_name)}"
                    artifact_parent_refs.setdefault(artifact_key, []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture adapter {req_id} ({parent_adapter or 'unknown adapter'}) has no child owner."
                )
            continue

        if source_kind == "architecture_worker":
            for unit in units:
                responsibility = unit.get("responsibility", "").casefold()
                if not any(marker in responsibility for marker in ("worker", "scheduler", "定时", "调度", "作业")):
                    continue
                unit_name = unit.get("name", "")
                owners[req_id].add(unit_name)
                artifact_parent_refs.setdefault("worker", []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture worker obligation {req_id} has no child worker owner."
                )
            continue

        if source_kind == "architecture_runtime":
            owners[req_id] = {
                unit.get("name", "") for unit in units if unit.get("name")
            }
            for unit_name in owners[req_id]:
                artifact_parent_refs.setdefault(f"runtime:{unit_name}", []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture runtime obligation {req_id} has no child integration owner."
                )
            continue

        if source_kind == "architecture_observability":
            for unit in units:
                if not unit.get("metric_contracts"):
                    continue
                unit_name = unit.get("name", "")
                owners[req_id].add(unit_name)
                artifact_parent_refs.setdefault(f"observability:{unit_name}", []).append(req_id)
            if not owners[req_id]:
                gaps.append(
                    f"Parent architecture observability obligation {req_id} has no child metric owner."
                )
            continue

        owners[req_id] = {
            unit.get("name", "")
            for unit in units
            if _requirement_matches_unit(req, unit, [])
        }
        if not owners[req_id]:
            gaps.append(
                f"Parent architecture obligation {req_id} has no child owner."
            )

    return owners, interface_parent_refs, data_parent_refs, artifact_parent_refs, gaps


def _propagate_frontend_business_ownership(
    business_requirements: list[dict],
    architecture_requirements: list[dict],
    architecture_owners: dict[str, set[str]],
    requirement_owners: dict[str, set[str]],
    gaps: list[str],
) -> None:
    business_by_id = {
        req.get("id", ""): req
        for req in business_requirements
        if req.get("id")
    }
    for architecture_req in architecture_requirements:
        if architecture_req.get("source_kind") != "architecture_frontend":
            continue
        architecture_id = architecture_req.get("id", "")
        linked_ids = list(architecture_req.get("related_reqs", []))
        if not linked_ids:
            linked_ids = [
                req_id
                for req_id in re.findall(
                    r"\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\b",
                    architecture_req.get("text", ""),
                )
                if req_id in business_by_id
            ]
        if not linked_ids:
            linked_ids = [
                req_id
                for req_id, req in business_by_id.items()
                if "frontend" in req.get("implementation_surfaces", [])
            ]
        if not linked_ids:
            gaps.append(
                f"Parent architecture frontend obligation {architecture_id or 'UNKNOWN'} is not linked "
                "to any parent business requirement."
            )
            continue
        for linked_id in linked_ids:
            if linked_id not in business_by_id:
                gaps.append(
                    f"Parent architecture frontend obligation {architecture_id or 'UNKNOWN'} references "
                    f"unknown business requirement {linked_id}."
                )
                continue
            requirement_owners.setdefault(linked_id, set()).update(
                architecture_owners.get(architecture_id, set())
            )


def _unit_has_explicit_frontend_owner(unit: dict) -> bool:
    evidence_text = " ".join(
        str(item.get("text", ""))
        for item in unit.get("evidence", [])
        if isinstance(item, dict)
    )
    text = " ".join(
        [
            str(unit.get("name", "")),
            str(unit.get("responsibility", "")),
            str(unit.get("partition_reason", "")),
            *[str(item) for item in unit.get("included_contexts", [])],
            evidence_text,
        ]
    ).casefold()
    markers = (
        "frontend",
        "front-end",
        "web app",
        "web ui",
        "user interface",
        "student app",
        "browser",
        "client app",
        "react",
        "vue",
        "angular",
        "svelte",
        "前端",
        "网页",
        "页面",
        "界面",
        "浏览器",
        "客户端",
        "学生端",
        "交互层",
    )
    return any(marker in text for marker in markers)


def _requirement_matches_unit(req: dict, unit: dict, scenarios: list[dict]) -> bool:
    req_id = req.get("id", "")
    req_text = req.get("text", "")
    combined_text = req_text
    responsibility = unit.get("responsibility", "")
    if _violates_module_ownership(combined_text, responsibility):
        return False

    evidence_text = " ".join(
        item.get("text", "")
        for item in unit.get("evidence", [])
        if isinstance(item, dict)
    )
    if req_id and req_id in evidence_text:
        return True

    normalized_text = _normalize_keyword(combined_text)
    explicit_names = [unit.get("name", "")] + unit.get("included_contexts", [])
    if any(
        name and _normalize_keyword(name) in normalized_text
        for name in explicit_names
    ):
        return True
    if _semantic_match({**req, "text": combined_text}, unit):
        return True

    unit_text = " ".join(
        [unit.get("responsibility", ""), unit.get("partition_reason", "")]
        + unit.get("included_contexts", [])
        + unit.get("related_aggregates", [])
        + [str(dependency.get("name", "")) for dependency in unit.get("dependencies", [])]
        + [str(event.get("event_name", "")) for event in unit.get("events", [])]
        + [
            " ".join(
                [
                    interface.get("name", ""),
                    " ".join(interface.get("request_fields", [])),
                    " ".join(interface.get("response_fields", [])),
                    " ".join(interface.get("error_codes", [])),
                ]
            )
            for interface in unit.get("interfaces", [])
            if isinstance(interface, dict)
        ]
    )
    return len(_generic_semantic_tokens(unit_text) & _generic_semantic_tokens(combined_text)) >= 2


def _propagate_scenario_co_ownership(
    owners: dict[str, set[str]],
    scenarios: list[dict],
) -> None:
    """Recover an otherwise-unowned requirement from a jointly tagged scenario."""
    changed = True
    while changed:
        changed = False
        for scenario in scenarios:
            req_ids = [req_id for req_id in scenario.get("requirement_ids", []) if req_id in owners]
            inherited = set().union(*(owners.get(req_id, set()) for req_id in req_ids))
            if not inherited:
                continue
            for req_id in req_ids:
                if owners.get(req_id):
                    continue
                owners[req_id] = set(inherited)
                changed = True


def _scenario_text(scenario: dict) -> str:
    return " ".join(
        [scenario.get("feature", ""), scenario.get("scenario", "")]
        + [step.get("text", "") for step in scenario.get("steps", []) if isinstance(step, dict)]
    )


def _generic_semantic_tokens(text: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    expanded = expanded.replace("_", " ").replace("-", " ")
    latin = {
        token.casefold().rstrip("s")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", expanded)
        if len(token) >= 3
        and token.casefold() not in {"module", "component", "service", "system", "shall", "should"}
    }
    cjk: set[str] = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (3, 4):
            for index in range(len(chunk) - size + 1):
                token = chunk[index:index + size]
                if token not in _STOP_TERMS:
                    cjk.add(token)
    return latin | cjk


def _is_derive_control_nfr(nfr: dict) -> bool:
    normalized = _normalize_keyword(nfr.get("text", ""))
    return "派生prdmusthave数量" in normalized or "deriveprdmusthavecount" in normalized


def _is_derive_control_metric(metric: dict) -> bool:
    normalized = _normalize_keyword(metric.get("name", ""))
    return normalized in {"musthave范围预算", "父需求追溯覆盖率", "派生覆盖完整率"}


def _nfr_requires_observability(nfr: dict) -> bool:
    text = nfr.get("text", "").casefold()
    return bool(
        re.search(r"\b(?:p\d{2}|slo|sla)\b|%|成功率|可追溯|审计|测量|日志|指标", text)
    )


def _external_dependencies(dependencies: list[dict]) -> list[dict]:
    external_markers = (
        "acl",
        "gateway",
        "objectstorage",
        "s3",
        "minio",
        "llm",
        "ocr",
        "recognitionservice",
        "sms",
        "第三方",
        "外部服务",
    )
    result = []
    seen: set[str] = set()
    for dependency in dependencies:
        if dependency.get("relationship") == "consumer":
            continue
        name = str(dependency.get("name", ""))
        normalized = _normalize_keyword(name)
        if not normalized or not any(marker in normalized for marker in external_markers):
            continue
        canonical = normalized
        if any(marker in normalized for marker in ("objectstorage", "s3", "minio")):
            canonical = "objectstorage"
        elif "sms" in normalized:
            canonical = "smsgateway"
        elif "llm" in normalized:
            canonical = "llmservice"
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(dependency)
    return result


_SURFACE_ORDER = [
    "frontend",
    "api_backend",
    "domain_logic",
    "database_migration",
    "worker_job",
    "external_adapter",
    "observability",
    "integration_wiring",
]


def _detect_implementation_surfaces(text: str, scenarios: list[dict]) -> list[str]:
    combined = f"{text} {' '.join(_surface_scenario_text(scenario) for scenario in scenarios)}"
    lowered = combined.casefold()
    surfaces = {"domain_logic"}
    if _has_user_interaction(lowered) or any(
        marker in lowered
        for marker in (
            "frontend",
            "front-end",
            "web app",
            "user interface",
            "前端",
            "页面",
            "界面",
            "按钮",
            "浏览器",
            "展示",
            "显示",
            "错误提示",
            "学生点击",
            "学生选择",
            "学生上传",
            "学生输入",
            "学生填写",
            "学生提交",
            "学生请求",
            "用户点击",
            "用户选择",
            "用户上传",
            "用户输入",
            "用户填写",
            "用户提交",
            "用户请求",
            "student clicks",
            "student selects",
            "student uploads",
            "student enters",
            "student submits",
            "student requests",
            "user clicks",
            "user selects",
            "user uploads",
            "user enters",
            "user submits",
            "user requests",
        )
    ):
        surfaces.add("frontend")
    if any(
        marker in lowered
        for marker in (
            "backend",
            "api",
            "endpoint",
            "request",
            "response",
            "后端",
            "接口",
            "请求",
            "响应",
            "错误码",
        )
    ):
        surfaces.add("api_backend")
    if any(marker in lowered for marker in ("database", "postgres", "schema", "migration", "数据库", "迁移")):
        surfaces.add("database_migration")
    if any(marker in lowered for marker in ("worker", "scheduler", "cron", "定时", "调度", "作业")):
        surfaces.add("worker_job")
    if any(marker in lowered for marker in (" acl", "gateway", "external", "第三方", "外部服务")):
        surfaces.add("external_adapter")
    return [surface for surface in _SURFACE_ORDER if surface in surfaces]


def _surface_scenario_text(scenario: dict) -> str:
    parts = [scenario.get("feature", ""), scenario.get("scenario", "")]
    phase = ""
    for step in scenario.get("steps", []):
        if not isinstance(step, dict):
            continue
        keyword = str(step.get("keyword", "")).casefold()
        if keyword in {"given", "when", "then"}:
            phase = keyword
        if phase != "given":
            parts.append(str(step.get("text", "")))
    return " ".join(parts)


def _has_user_interaction(text: str) -> bool:
    actor_action_patterns = (
        r"(?:学生|用户).{0,24}(?:点击|选择|上传|输入|填写|提交|请求|确认|重试|查看|进入|开始|添加|删除|下载|登录|退出)",
        r"(?:student|user).{0,40}(?:clicks?|selects?|uploads?|enters?|fills?|submits?|requests?|confirms?|retries|views?|opens?|starts?|adds?|removes?|downloads?|logs? in|signs? in|logs? out)",
    )
    return any(re.search(pattern, text) for pattern in actor_action_patterns)


def _module_implementation_surfaces(
    module: dict,
    requirements: list[dict],
    scenarios: list[dict],
    interfaces: list[dict],
    dependencies: list[dict],
    data_assets: list[dict],
) -> list[str]:
    text = " ".join(
        [module.get("name", ""), module.get("responsibility", "")]
        + [req.get("text", "") for req in requirements]
    )
    surfaces = set(_detect_implementation_surfaces(text, scenarios))
    if interfaces:
        surfaces.add("api_backend")
    if data_assets:
        surfaces.add("database_migration")
    if _external_dependencies(dependencies):
        surfaces.add("external_adapter")
    if any(marker in text.casefold() for marker in ("worker", "scheduler", "定时", "调度")):
        surfaces.add("worker_job")
    return [surface for surface in _SURFACE_ORDER if surface in surfaces]


def _module_keywords(module: dict) -> list[str]:
    keywords: list[str] = [module.get("name", ""), module.get("responsibility", "")]
    keywords.extend(module.get("included_contexts", []))
    keywords.extend(module.get("related_aggregates", []))
    for interface in module.get("interfaces", []):
        if isinstance(interface, dict):
            keywords.append(interface.get("name", ""))
    for dependency in module.get("dependencies", []):
        if isinstance(dependency, dict):
            keywords.append(dependency.get("name", ""))
    return [_normalize_keyword(keyword) for keyword in keywords if keyword]


def _normalize_keyword(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


_STOP_TERMS = {
    "系统",
    "模块",
    "支持",
    "提供",
    "管理",
    "学生",
    "数据",
    "中心",
    "生命周期",
    "接口",
    "统一",
    "核心",
    "职责",
}


def _semantic_match(req: dict, module: dict) -> bool:
    """Match Chinese parent requirements to module responsibility text.

    Architecture packages often name modules in English while root PRDs describe
    behavior in Chinese. A narrow character n-gram overlap on the module's
    responsibility gives Derive enough ownership signal without requiring a
    Leaf Gate report or manual mapping.
    """
    req_text = req.get("text", "")
    responsibility = module.get("responsibility", "")
    if _violates_module_ownership(req_text, responsibility):
        return False
    concept_matches = _matches_responsibility_concept(req_text, responsibility)
    if _is_problem_intake_component_responsibility(responsibility):
        return concept_matches
    if concept_matches:
        return True

    terms = _semantic_terms(module)
    if not terms:
        return False

    return any(len(term) >= 4 and term in req_text for term in terms)


def _violates_module_ownership(req_text: str, responsibility: str) -> bool:
    if _is_problem_intake_component_responsibility(responsibility):
        return False
    if _is_identity_requirement(req_text) and not _owns_identity(responsibility):
        return True
    if _is_retention_or_training_requirement(req_text):
        return not _owns_compliance(responsibility)
    if _is_tutoring_session_gate_requirement(req_text):
        return not _owns_tutoring_session(responsibility)
    if _is_problem_intake_requirement(req_text) and not _owns_problem_intake(responsibility):
        return True
    if _is_privacy_prompt_requirement(req_text) and not _owns_problem_intake(responsibility):
        return True
    return _violates_generation_ownership(req_text, responsibility)


def _is_problem_intake_component_responsibility(responsibility: str) -> bool:
    return any(
        checker(responsibility)
        for checker in (
            _owns_consent_component,
            _owns_image_submission_component,
            _owns_image_validation_component,
            _owns_math_recognition_component,
            _owns_session_lifecycle_component,
        )
    )


def _violates_generation_ownership(req_text: str, responsibility: str) -> bool:
    """Prevent content-generation requirements from matching intake-style modules."""
    if _is_prompt_content_requirement(req_text) and not _owns_ai_tutoring(responsibility):
        return True
    if _is_solution_content_requirement(req_text) and not _owns_ai_tutoring(responsibility):
        return True

    generation_markers = ("完整解答", "分层提示", "关键推导", "标准术语")
    if not any(marker in req_text for marker in generation_markers):
        return False

    if "标准术语" in req_text or "关键推导" in req_text:
        owner_markers = ("完整解答", "分层提示", "提示模板", "LLM")
        return not any(marker in responsibility for marker in owner_markers)

    owner_markers = ("完整解答", "分层提示", "解答请求", "提示轮次", "提示模板", "LLM")
    return not any(marker in responsibility for marker in owner_markers)


def _matches_responsibility_concept(req_text: str, responsibility: str) -> bool:
    if _owns_consent_component(responsibility):
        return _is_privacy_prompt_requirement_plain(req_text)

    if _owns_image_submission_component(responsibility):
        return _is_image_upload_requirement_plain(req_text) or _is_image_count_requirement_plain(req_text)

    if _owns_image_validation_component(responsibility):
        return _is_image_validation_requirement_plain(req_text)

    if _owns_math_recognition_component(responsibility):
        return _is_math_recognition_requirement_plain(req_text)

    if _owns_session_lifecycle_component(responsibility):
        return _is_retention_requirement_plain(req_text)

    if _owns_identity(responsibility):
        return (
            ("手机号" in req_text and ("登录" in req_text or "验证码" in req_text))
            or ("验证码" in req_text and any(marker in req_text for marker in ("生成", "有效", "重发", "输错", "失效")))
        )

    if _owns_problem_intake(responsibility):
        return (
            _is_problem_intake_requirement(req_text)
            or _is_privacy_prompt_requirement(req_text)
        )

    if _owns_tutoring_session(responsibility):
        return (
            ("基础水平" in req_text and any(marker in req_text for marker in ("选择", "开始答疑", "未选择")))
            or _is_tutoring_session_gate_requirement(req_text)
            or ("完整解答" in req_text and any(marker in req_text for marker in ("查看", "点击", "按钮", "请求", "展示")))
            or ("会话" in req_text and any(marker in req_text for marker in ("启动", "开始", "关闭", "结束", "生命周期", "状态")))
        )

    if _owns_ai_tutoring(responsibility):
        return (
            _is_prompt_content_requirement(req_text)
            or _is_solution_content_requirement(req_text)
            or ("提示" in req_text and "标准术语" in req_text)
        )

    if _owns_compliance(responsibility):
        return _is_retention_or_training_requirement(req_text)

    return False


def _owns_identity(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("手机号登录", "短信验证码", "认证会话"))


def _owns_problem_intake(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("图片上传", "格式/大小", "有效数学题识别", "图片元数据", "隐私提示"))


def _owns_tutoring_session(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("基础水平选择", "会话生命周期", "提示轮次计数", "解答请求门控"))


def _owns_ai_tutoring(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("生成分层提示", "完整解答", "LLM", "提示模板"))


def _owns_compliance(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("保留策略", "定时删除", "合规审计", "训练使用禁止"))


def _owns_consent_component(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("隐私提示展示", "学生确认", "同意记录", "PrivacyConsent"))


def _owns_image_submission_component(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("图片集提交", "数量限制", "对象存储写入", "ImageSubmission", "RawImage"))


def _owns_image_validation_component(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("格式校验", "大小校验", "损坏检测"))


def _owns_math_recognition_component(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("识别服务", "识别结果", "MathProblemRecognition"))


def _owns_session_lifecycle_component(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("会话创建", "状态管理", "完成判定", "保存期过期", "ProblemIntakeSession"))


def _is_privacy_prompt_requirement_plain(req_text: str) -> bool:
    return "隐私提示" in req_text and any(marker in req_text for marker in ("上传前", "展示", "说明"))


def _is_image_upload_requirement_plain(req_text: str) -> bool:
    return "上传" in req_text and "图片" in req_text and any(marker in req_text for marker in ("JPG", "PNG", "答疑输入"))


def _is_image_count_requirement_plain(req_text: str) -> bool:
    return "图片" in req_text and any(marker in req_text for marker in ("3 张", "第 4 张", "数量超限", "超过 3 张"))


def _is_image_validation_requirement_plain(req_text: str) -> bool:
    if _is_image_count_requirement_plain(req_text):
        return False
    return "图片" in req_text and any(
        marker in req_text
        for marker in ("10MB", "损坏", "非 JPG/PNG", "无法识别", "错误提示", "拒绝")
    )


def _is_math_recognition_requirement_plain(req_text: str) -> bool:
    return any(marker in req_text for marker in ("无法识别有效高中数学题", "有效高中数学题", "明确求解目标", "识别出至少一个"))


def _is_retention_requirement_plain(req_text: str) -> bool:
    return any(marker in req_text for marker in ("T + 30", "不可读取", "保存时间", "保存期过期"))


def _is_identity_requirement(req_text: str) -> bool:
    return "验证码" in req_text or ("手机号" in req_text and "登录" in req_text)


def _is_problem_intake_requirement(req_text: str) -> bool:
    if "图片" not in req_text:
        return False
    return any(
        marker in req_text
        for marker in ("上传", "JPG", "PNG", "10MB", "损坏", "有效高中数学题", "识别", "最多", "第 4 张", "第4张")
    )


def _is_privacy_prompt_requirement(req_text: str) -> bool:
    return "隐私提示" in req_text and ("上传前" in req_text or "展示" in req_text)


def _is_retention_or_training_requirement(req_text: str) -> bool:
    if _is_privacy_prompt_requirement(req_text):
        return False
    return any(marker in req_text for marker in ("30 天", "30天", "删除", "不可读取", "保存时间", "保留", "模型训练"))


def _is_tutoring_session_gate_requirement(req_text: str) -> bool:
    if "基础水平" in req_text and any(marker in req_text for marker in ("选择", "开始答疑", "未选择")):
        return "生成分层提示" not in req_text
    if ("分层提示" in req_text or "提示轮次" in req_text) and any(
        marker in req_text for marker in ("轮次", "上限", "成功展示", "失败不计入")
    ):
        return True
    if "提示轮次" in req_text and "记录" in req_text:
        return True
    if "完整解答" in req_text and any(marker in req_text for marker in ("查看", "点击", "按钮", "请求")):
        return not any(marker in req_text for marker in ("生成响应", "按步骤", "关键推导", "标准术语"))
    return False


def _is_prompt_content_requirement(req_text: str) -> bool:
    if "分层提示" not in req_text and "提示" not in req_text:
        return False
    return any(
        marker in req_text
        for marker in ("生成分层提示", "提示生成", "生成提示", "每一轮分层提示", "提示方向", "追问问题", "关键计算结果", "前置知识", "关键思路", "突破口", "易错提醒")
    )


def _is_solution_content_requirement(req_text: str) -> bool:
    if "完整解答" not in req_text:
        return False
    return any(marker in req_text for marker in ("生成响应", "生成", "按步骤", "关键推导", "标准术语"))


def _semantic_terms(module: dict) -> set[str]:
    source_parts = [
        module.get("responsibility", ""),
        module.get("partition_reason", ""),
        " ".join(module.get("included_contexts", [])),
    ]
    terms: set[str] = set()
    for text in source_parts:
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if chunk in _STOP_TERMS:
                continue
            if 2 <= len(chunk) <= 8:
                terms.add(chunk)
            for size in (4,):
                for index in range(0, max(len(chunk) - size + 1, 0)):
                    term = chunk[index:index + size]
                    if term not in _STOP_TERMS:
                        terms.add(term)

    return terms
