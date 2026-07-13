"""Validation for the PRD-to-test oracle handoff contract."""
from __future__ import annotations

from collections import defaultdict


FUNCTIONAL_REQUIRED_FIELDS = (
    "actor",
    "preconditions",
    "trigger",
    "response",
    "observable_oracles",
    "boundaries",
    "exceptions",
)

NFR_REQUIRED_FIELDS = (
    "population",
    "measurement_start",
    "measurement_end",
    "unit",
    "threshold",
    "exclusions",
    "pass_rule",
)

VALID_RELEASE_SCOPES = {"current", "out_of_version", "not_applicable"}


def release_scope(item: dict) -> str:
    """Return the normalized release scope; legacy records default to current."""
    return item.get("release_scope", "current")


def is_current(item: dict) -> bool:
    return release_scope(item) == "current"


def _is_present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def validate_acceptance_contract(contract: dict) -> list[str]:
    """Return missing/invalid fields without inventing any business behavior."""
    issues: list[str] = []
    contract_id = contract.get("id") or contract.get("ac_id")
    if not _is_present(contract_id):
        issues.append("missing id")
    verifies = contract.get("verifies", [])
    if isinstance(verifies, str):
        verifies = [verifies]
    if not verifies:
        issues.append("missing verifies")

    scope = release_scope(contract)
    if scope not in VALID_RELEASE_SCOPES:
        issues.append(f"invalid release_scope: {scope}")
    if scope != "current":
        return issues

    contract_type = contract.get("type", "functional")
    required = NFR_REQUIRED_FIELDS if contract_type == "nfr" else FUNCTIONAL_REQUIRED_FIELDS
    for field in required:
        if not _is_present(contract.get(field)):
            issues.append(f"missing {field}")
    if contract_type == "functional":
        for field in ("boundaries", "exceptions"):
            for index, item in enumerate(contract.get(field, [])):
                complete_pair = (
                    isinstance(item, dict)
                    and _is_present(item.get("condition"))
                    and _is_present(item.get("response"))
                ) or (
                    isinstance(item, str)
                    and any(separator in item for separator in ("->", "=>", "→"))
                )
                if not complete_pair:
                    issues.append(f"incomplete {field}[{index}] condition/response pair")
    if not _is_present(contract.get("evidence_refs")):
        issues.append("missing evidence_refs")
    return issues


def check_oracle_coverage(requirements: dict, contracts: list[dict]) -> list[dict]:
    """Find current-scope clauses that lack a complete explicit acceptance oracle."""
    contract_by_req: dict[str, list[dict]] = defaultdict(list)
    for contract in contracts:
        verifies = contract.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        for req_id in verifies:
            contract_by_req[req_id].append(contract)

    gaps: list[dict] = []
    all_requirements = [
        *(dict(item, requirement_type="functional") for item in requirements.get("functional", [])),
        *(dict(item, requirement_type="nfr") for item in requirements.get("non_functional", [])),
    ]
    for requirement in all_requirements:
        if not is_current(requirement):
            if not _is_present(requirement.get("scope_reason")):
                gaps.append({
                    "id": requirement.get("id", ""),
                    "type": requirement["requirement_type"],
                    "reason": "non-current requirement missing scope_reason",
                })
            continue
        req_id = requirement.get("id", "")
        expected_type = requirement["requirement_type"]
        linked = contract_by_req.get(req_id, [])
        complete = [
            contract for contract in linked
            if contract.get("type", "functional") == expected_type
            and not validate_acceptance_contract(contract)
        ]
        if not complete:
            reasons = []
            for contract in linked:
                reasons.extend(validate_acceptance_contract(contract))
            gaps.append({
                "id": req_id,
                "type": expected_type,
                "reason": "; ".join(sorted(set(reasons))) if reasons else "no linked acceptance contract",
            })
    return gaps


def build_coverage_ledger(requirements: dict, contracts: list[dict]) -> list[dict]:
    """Build a machine-checkable coverage ledger for every requirement clause."""
    gaps = {item["id"]: item["reason"] for item in check_oracle_coverage(requirements, contracts)}
    rows: list[dict] = []
    for item_type, key in (("functional", "functional"), ("nfr", "non_functional")):
        for requirement in requirements.get(key, []):
            req_id = requirement.get("id", "")
            linked_ids = []
            for contract in contracts:
                verifies = contract.get("verifies", [])
                if isinstance(verifies, str):
                    verifies = [verifies]
                if req_id in verifies:
                    linked_ids.append(contract.get("id") or contract.get("ac_id") or "UNKNOWN")
            scope = release_scope(requirement)
            status = "blocked" if req_id in gaps else ("excluded" if scope != "current" else "ready")
            rows.append({
                "requirement_id": req_id,
                "type": item_type,
                "release_scope": scope,
                "contract_ids": linked_ids,
                "status": status,
                "reason": gaps.get(req_id, requirement.get("scope_reason", "")),
            })
    return rows
