"""Full-layer parent-to-child allocation for Derive mode."""
from __future__ import annotations

from pathlib import Path

from prd_flow.derive.context_builder import build_derive_context
from prd_flow.derive.parser import extract_architecture_catalog, parse_parent_prd


def build_layer_allocation(
    parent_prd_path: Path,
    architecture_package_path: Path,
    target_granularity: str = "deployable_module",
) -> dict:
    """Allocate every parent obligation before generating any child PRD."""
    parent = parse_parent_prd(parent_prd_path)
    catalog = extract_architecture_catalog(architecture_package_path, target_granularity)
    excluded_ids = set(catalog.get("excluded_requirement_refs", []))
    target_modules = [
        unit.get("name", "")
        for unit in catalog.get("units", [])
        if unit.get("name")
    ]
    contexts: dict[str, dict] = {}
    errors: list[str] = []

    for module_name in target_modules:
        context = build_derive_context(
            parent_prd_path,
            architecture_package_path,
            module_name,
            target_granularity=target_granularity,
        )
        contexts[module_name] = context
        if not context.get("success"):
            errors.append(context.get("error") or f"Unable to build context for {module_name}.")

    typed_items = [
        *(("requirement", item) for item in parent.get("requirements", [])),
        *(("non_functional", item) for item in parent.get("non_functional", [])),
    ]
    known_ids = {item.get("id", "") for _kind, item in typed_items if item.get("id")}
    owner_map: dict[str, set[str]] = {item_id: set() for item_id in known_ids}
    for module_name, context in contexts.items():
        for item_id, owners in context.get("requirement_owners", {}).items():
            if item_id in owner_map and module_name in owners:
                owner_map[item_id].add(module_name)

    ledger: list[dict] = []
    for kind, item in typed_items:
        item_id = item.get("id", "")
        if not item_id:
            continue
        owners = sorted(owner_map.get(item_id, set()))
        excluded = item_id in excluded_ids or item.get("release_scope", "current") != "current"
        ledger.append({
            "id": item_id,
            "kind": kind,
            "release_scope": item.get("release_scope", "current"),
            "owners": owners,
            "status": "excluded" if excluded else ("allocated" if owners else "unassigned"),
        })
        if not owners and not excluded:
            errors.append(f"Parent {kind} {item_id} has no child owner.")

    for contract in parent.get("acceptance_contracts", []):
        verifies = contract.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        unknown = sorted(set(verifies) - known_ids)
        owners = sorted(set().union(*(owner_map.get(item_id, set()) for item_id in verifies))) if verifies else []
        ledger.append({
            "id": contract.get("id", "UNKNOWN"),
            "kind": "acceptance_contract",
            "verifies": verifies,
            "owners": owners,
            "status": "allocated" if owners and not unknown else "unassigned",
        })
        if unknown:
            errors.append(
                f"Acceptance contract {contract.get('id', 'UNKNOWN')} references unknown requirements: {', '.join(unknown)}."
            )
        elif not owners:
            errors.append(f"Acceptance contract {contract.get('id', 'UNKNOWN')} has no child owner.")

    metric_owner_map: dict[str, set[str]] = {}
    for module_name, context in contexts.items():
        for metric in context.get("related_success_metrics", []):
            metric_id = metric.get("id") or metric.get("name", "UNKNOWN")
            metric_owner_map.setdefault(metric_id, set()).add(module_name)
    for metric in parent.get("success_metrics", []):
        metric_id = metric.get("id") or metric.get("name", "UNKNOWN")
        owners = sorted(metric_owner_map.get(metric_id, set()))
        ledger.append({
            "id": metric_id,
            "kind": "success_metric",
            "owners": owners,
            "status": "allocated" if owners else "unassigned",
        })
        if not owners:
            errors.append(f"Success metric {metric_id} has no child owner.")

    errors = list(dict.fromkeys(error for error in errors if error))
    return {
        "success": bool(target_modules) and not errors,
        "parent_doc_id": parent.get("doc_id", "UNKNOWN"),
        "target_granularity": target_granularity,
        "target_modules": target_modules,
        "contexts": contexts,
        "ledger": ledger,
        "coverage_complete": bool(ledger) and all(row["status"] in {"allocated", "excluded"} for row in ledger),
        "errors": errors,
    }
