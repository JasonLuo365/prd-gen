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
    parent_frontmatter = parent_prd.get("frontmatter", {})
    if parent_frontmatter.get("status") == "draft" or parent_frontmatter.get("ready_for_test_generation") is False:
        return {
            "success": False, "parent_doc_id": parent_doc_id, "module_name": target_module,
            "available_modules": [], "target_granularity": target_granularity,
            "error": "PARENT_PRD_NOT_HANDOFF_READY: draft or blocked parents cannot be derived.",
        }

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
            "related_acceptance_contracts": [],
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
    architecture_excluded_ids = set(catalog.get("excluded_requirement_refs", []))
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
    # Architecture is allocation/reference evidence, never a source of product
    # requirements.  Discard legacy architecture-generated rows as obligations.
    parent_architecture_requirements: list[dict] = []
    business_requirements = [
        req for req in all_requirements
        if not str(req.get("source_kind", "")).startswith("architecture_")
    ]
    all_non_functional = parent_prd.get("non_functional", [])
    all_success_metrics = [
        metric
        for metric in parent_prd.get("success_metrics", [])
        if not _is_derive_control_metric(metric)
    ]
    non_goals = parent_prd.get("non_goals", [])
    acceptance_scenarios = parent_prd.get("acceptance_scenarios", [])
    acceptance_contracts = parent_prd.get("acceptance_contracts", [])
    requirement_owners = _build_ownership_map(
        business_requirements + all_non_functional,
        units,
        acceptance_scenarios,
    )
    _complete_atomic_aggregate_ownership(business_requirements, requirement_owners, units)
    for requirement_id in architecture_excluded_ids:
        requirement_owners[requirement_id] = set()
    for requirement in [*business_requirements, *all_non_functional]:
        parent_id = requirement.get("parent_req") or requirement.get("parent_nfr")
        if parent_id:
            inherited_owners = requirement_owners.get(requirement.get("id", ""), set())
            requirement_owners.setdefault(parent_id, set()).update(inherited_owners)
            clause_match = re.match(r"^CLAUSE-(\d{3})-", parent_id, re.IGNORECASE)
            if clause_match:
                requirement_owners.setdefault(
                    f"REQ-{clause_match.group(1)}",
                    set(),
                ).update(inherited_owners)
    architecture_owners: dict[str, set[str]] = {}
    interface_parent_refs: dict[str, list[str]] = {}
    data_parent_refs: dict[str, list[str]] = {}
    artifact_parent_refs: dict[str, list[str]] = {}
    architecture_parent_gaps: list[str] = []
    _propagate_scenario_co_ownership(requirement_owners, acceptance_scenarios)

    unit_names = {unit.get("name", "") for unit in units if unit.get("name")}
    metric_items = [
        {
            "id": metric.get("id") or f"METRIC-{index:03d}",
            "text": f"{metric.get('name', '')} {metric.get('method', '')}",
        }
        for index, metric in enumerate(all_success_metrics, start=1)
    ]
    metric_owners = _map_success_metric_owners(
        all_success_metrics,
        metric_items,
        units,
        requirement_owners,
    )
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
        if nfr.get("id", "") in architecture_excluded_ids or nfr.get("release_scope", "current") != "current":
            requirement_owners[nfr.get("id", "")] = set()
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
        and req.get("id", "") not in architecture_excluded_ids
        and req.get("release_scope", "current") == "current"
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
    related_acceptance_contracts = [
        contract
        for contract in acceptance_contracts
        if related_ids.intersection(
            contract.get("verifies", [])
            if isinstance(contract.get("verifies", []), list)
            else [contract.get("verifies")]
        )
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
        excluded_ids=architecture_excluded_ids,
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
        "related_acceptance_contracts": related_acceptance_contracts,
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
        "architecture_excluded_requirements": sorted(architecture_excluded_ids),
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
    excluded_ids: set[str] | None = None,
) -> list[dict]:
    """Describe where every parent obligation is expected to be inherited."""
    ledger: list[dict] = []
    excluded_ids = excluded_ids or set()
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
        if item_id in excluded_ids or item.get("release_scope", "current") != "current":
            status = "excluded"
        elif target_owner in owners:
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
        reference_ids = _requirement_reference_ids(req)
        explicit_owners = {
            unit.get("name", "")
            for unit in units
            if unit.get("name")
            and reference_ids.intersection(unit.get("requirement_refs", []))
        }
        if explicit_owners:
            owners[req_id] = explicit_owners
            continue
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


def _requirement_reference_ids(req: dict) -> set[str]:
    """Return IDs that an architecture allocation may use for one requirement."""
    ids = {str(req.get("id", "")), str(req.get("parent_req", "")), str(req.get("parent_nfr", ""))}
    for item_id in list(ids):
        clause_match = re.match(r"^CLAUSE-(\d{3})-", item_id, re.IGNORECASE)
        if clause_match:
            ids.add(f"REQ-{clause_match.group(1)}")
    return {item_id for item_id in ids if item_id}


def _complete_atomic_aggregate_ownership(
    requirements: list[dict],
    owners: dict[str, set[str]],
    units: list[dict],
) -> None:
    """Keep sibling atomic clauses together when architecture owns the parent capability."""
    by_parent: dict[str, list[str]] = {}
    for requirement in requirements:
        parent_id = requirement.get("parent_req")
        if parent_id:
            by_parent.setdefault(parent_id, []).append(requirement.get("id", ""))
    for requirement_ids in by_parent.values():
        records = [
            next((req for req in requirements if req.get("id") == item_id), {})
            for item_id in requirement_ids
        ]
        parent_text = next((record.get("parent_text", "") for record in records if record.get("parent_text")), "")
        scored = [
            (_ownership_overlap_score(parent_text, unit), unit.get("name", ""))
            for unit in units
            if unit.get("name")
        ]
        best_score = max((score for score, _name in scored), default=0)
        if best_score > 0:
            sibling_owners = {name for score, name in scored if score == best_score}
        else:
            sibling_owners = set().union(*(owners.get(item_id, set()) for item_id in requirement_ids))
        if not sibling_owners:
            continue
        for item_id in requirement_ids:
            owners[item_id] = set(sibling_owners)

    for requirement in requirements:
        item_id = requirement.get("id", "")
        if not item_id or owners.get(item_id) or requirement.get("parent_req"):
            continue
        scored = [
            (_ownership_overlap_score(requirement.get("text", ""), unit), unit.get("name", ""))
            for unit in units
            if unit.get("name")
        ]
        best_score = max((score for score, _name in scored), default=0)
        if best_score > 0:
            owners[item_id] = {name for score, name in scored if score == best_score}
        elif requirement.get("release_scope", "current") != "current":
            owners[item_id] = {unit.get("name", "") for unit in units if unit.get("name")}


def _ownership_overlap_score(text: str, unit: dict) -> int:
    """Score architecture responsibility overlap for otherwise-unowned capabilities."""
    unit_text = " ".join(
        [
            str(unit.get("name", "")),
            str(unit.get("responsibility", "")),
            *[str(item) for item in unit.get("included_contexts", [])],
        ]
    )
    return len(_ownership_terms(text) & _ownership_terms(unit_text))


def _ownership_terms(text: str) -> set[str]:
    terms = {
        token.casefold().rstrip("s")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text)
        if len(token) >= 3 and token.casefold() not in {"system", "module", "amazon"}
    }
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3, 4):
            for index in range(len(chunk) - size + 1):
                token = chunk[index:index + size]
                if token not in _STOP_TERMS:
                    terms.add(token)
    return terms


def _map_success_metric_owners(
    metrics: list[dict],
    metric_items: list[dict],
    units: list[dict],
    requirement_owners: dict[str, set[str]],
) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for metric, metric_item in zip(metrics, metric_items):
        verifies = metric.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        verified_owners = set().union(
            *(requirement_owners.get(requirement_id, set()) for requirement_id in verifies)
        ) if verifies else set()
        if verified_owners:
            owners[metric_item["id"]] = verified_owners
            continue
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


def _requirement_matches_unit(req: dict, unit: dict, scenarios: list[dict]) -> bool:
    req_id = req.get("id", "")
    req_text = req.get("text", "")
    combined_text = req_text
    parent_id = req.get("parent_req", "")
    if not parent_id:
        clause_match = re.match(r"CLAUSE-(\d{3})-", req_id, re.IGNORECASE)
        parent_id = f"REQ-{clause_match.group(1)}" if clause_match else req_id
    requirement_refs = set(unit.get("requirement_refs", []))
    if req_id in requirement_refs or parent_id in requirement_refs:
        return True

    evidence_text = " ".join(
        item.get("text", "")
        for item in unit.get("evidence", [])
        if isinstance(item, dict)
    )
    if (req_id and req_id in evidence_text) or (parent_id and parent_id in evidence_text):
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



def _detect_implementation_surfaces(text: str, scenarios: list[dict]) -> list[str]:
    """Expose no inferred implementation surface as a product obligation."""
    return ["domain_logic"]


def _module_implementation_surfaces(
    module: dict, requirements: list[dict], scenarios: list[dict], interfaces: list[dict],
    dependencies: list[dict], data_assets: list[dict],
) -> list[str]:
    """Keep architecture implementation details non-normative."""
    return ["domain_logic"]


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
    """Conservatively match only generic responsibility terms.

    Explicit allocations remain authoritative.  This fallback must never use a
    product/domain dictionary: ambiguity is a blocking allocation error.
    """
    req_text = req.get("text", "")
    terms = _semantic_terms(module)
    if not terms:
        return False
    return any(len(term) >= 4 and term in req_text for term in terms)


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
