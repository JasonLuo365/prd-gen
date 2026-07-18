"""Main CLI entry point for PRD Flow."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from prd_flow import yaml_utils as yaml
from prd_flow.mode_detector import Mode, detect_mode
from prd_flow.output.assembler import assemble_prd
from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.phases.problem_statement import ProblemStatementPhase
from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.quality.ambiguity import scan_ambiguity
from prd_flow.quality.reporter import format_quality_report
from prd_flow.quality.smart_req import check_smart_req
from prd_flow.quality.oracle import build_coverage_ledger, check_oracle_coverage
from prd_flow.quality.suggest import suggest_fix
from prd_flow.derive.context_builder import build_derive_context
from prd_flow.derive.layer_allocation import build_layer_allocation
from prd_flow.derive.parser import parse_parent_prd
from prd_flow.derive.decision_rules import find_best_module_match
from prd_flow.derive.quality_gates import check_parent_traceability
from prd_flow.session import SessionState, save_session, load_session

EXIT_SUCCESS = 0
EXIT_INPUT_ERROR = 1
EXIT_QUALITY_BLOCKED = 2
EXIT_DEPENDENCY_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_SCHEMA_INCOMPATIBLE = 5


class SchemaIncompatibleError(ValueError):
    """Raised when a supplied artifact cannot satisfy the PRD contract."""


def _run_smart_check(state: SessionState) -> list:
    """对P3的功能需求运行SMART-REQ检查。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    if state.mode == "derive":
        functional = [
            requirement
            for requirement in functional
            if requirement.get("source_kind") != "parent_requirement"
        ]
    contracts = state.draft_content.get("P4", {}).get("contracts")
    return [check_smart_req(req, contracts) for req in functional]


def _authoritative_derive_requirements(requirements: list[dict]) -> list[dict]:
    """Preserve every parent requirement and its original MoSCoW priority."""
    return list(requirements)


def _derived_requirement_id(kind: str, parent_id: str, used: set[str]) -> str:
    """Derive an ID from the stable parent ID, not the input list position."""
    suffix = re.sub(r"^(?:REQ|NFR)-", "", parent_id.upper()) or "UNKNOWN"
    candidate = f"{kind}-D{suffix}"
    if candidate in used:
        candidate = f"{candidate}-{hashlib.sha256(parent_id.encode('utf-8')).hexdigest()[:6].upper()}"
    used.add(candidate)
    return candidate


def _requirement_matches_parent_reference(requirement: dict, reference: str) -> bool:
    candidates = {
        str(requirement.get(key, ""))
        for key in ("id", "parent_req", "parent_nfr")
        if requirement.get(key)
    }
    if reference in candidates:
        return True
    aggregate = re.fullmatch(r"REQ-(\d+)", reference, re.IGNORECASE)
    return bool(aggregate) and any(
        candidate.upper().startswith(f"CLAUSE-{aggregate.group(1)}-")
        for candidate in candidates
    )


def _map_parent_references(
    references: list[str],
    parent_requirements: list[dict],
    direct_mapping: dict[str, str],
) -> list[str]:
    mapped: list[str] = []
    for reference in references:
        direct = direct_mapping.get(reference)
        if direct:
            mapped.append(direct)
            continue
        mapped.extend(
            direct_mapping[requirement.get("id", "")]
            for requirement in parent_requirements
            if requirement.get("id", "") in direct_mapping
            and _requirement_matches_parent_reference(requirement, reference)
        )
    return list(dict.fromkeys(mapped))


def _load_contract_projections(architecture_input: str | Path) -> dict[tuple[str, str], dict]:
    """Load current or legacy declarative projections without inventing contract data."""
    architecture_path = Path(architecture_input)
    if not architecture_path.is_dir():
        return {}
    projection_path = architecture_path / "acceptance-contract-projections.yaml"
    if not projection_path.exists():
        return {}
    payload = yaml.safe_load(projection_path.read_text(encoding="utf-8")) or {}
    records = list(payload.get("acceptance_contract_projections", []) or [])
    # Legacy architecture packages group shared projections by parent contract.
    # Normalize their explicit module slices to the current record-per-child shape.
    # Only `shared` is lossless: a legacy slice is not a complete child contract
    # and therefore cannot be treated as a `project` projection.
    for legacy in payload.get("contracts", []) or []:
        if legacy.get("disposition") != "shared":
            continue
        parent_contract = legacy.get("contract_id", "")
        for slice_record in legacy.get("module_slices", []) or []:
            target_module = slice_record.get("module_id", "")
            if target_module and parent_contract:
                records.append({
                    "target_module": target_module,
                    "parent_contract": parent_contract,
                    "mode": "shared",
                    # The legacy field explicitly records a parent-ledger
                    # association; it adds no child ownership or behavior.
                    "legacy_additional_verifies": legacy.get("ledger_also_covers", []) or [],
                })
    return {
        (str(record.get("target_module", "")), str(record.get("parent_contract", ""))): record
        for record in records
        if record.get("target_module") and record.get("parent_contract")
    }


def _check_oracle_coverage(state: SessionState) -> list[dict]:
    """Return current-scope functional and NFR clauses without complete oracles."""
    return check_oracle_coverage(
        state.draft_content.get("P3", {}),
        state.draft_content.get("P4", {}).get("contracts", []),
    )


def _normalize_inherited_contract_pairs(contract: dict) -> dict:
    """Preserve legacy prose pairs in the structured handoff representation."""
    normalized = dict(contract)
    for field in ("boundaries", "exceptions"):
        values = normalized.get(field, [])
        if isinstance(values, str):
            values = [values]
        pairs: list[object] = []
        for value in values:
            if not isinstance(value, str):
                pairs.append(value)
                continue
            separator = next((item for item in ("；", ";") if item in value), None)
            if not separator:
                pairs.append(value)
                continue
            condition, response = value.split(separator, 1)
            if condition.strip() and response.strip():
                pairs.append({"condition": condition.strip(), "response": response.strip()})
            else:
                pairs.append(value)
        normalized[field] = pairs
    if any(
        isinstance(value, str) and value.strip()
        for field in ("boundaries", "exceptions")
        for value in normalized.get(field, [])
    ):
        normalized["_inherited_legacy_pair_text"] = True
    return normalized


def _run_ambiguity_check(state: SessionState, prd_text: str) -> dict:
    """对PRD文本运行歧义扫描。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return scan_ambiguity(prd_text, functional)


def _ask_continue(prompt: str) -> bool:
    """询问用户是否继续。"""
    answer = input(f"{prompt} (y/n): ").strip().lower()
    return answer in ("y", "yes", "是")


def _canonical_hash(value: object) -> str:
    """Hash structured input deterministically for review and provenance."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _artifact_identity(state: SessionState, args: argparse.Namespace, *, include_extended: bool = True) -> dict:
    p1 = state.draft_content.setdefault("P1", {})
    run_id = getattr(args, "run_id", None) or p1.get("run_id") or f"run_{state.session_id}"
    project_id = getattr(args, "project_id", None) or p1.get("project_id") or p1.get("doc_id", "unknown")
    node_id = getattr(args, "node_id", None) or p1.get("node_id") or "root"
    parent_node_id = getattr(args, "parent_node_id", None) or p1.get("parent_node_id")
    p1.update({
        "run_id": run_id, "project_id": project_id, "node_id": node_id,
        "parent_node_id": parent_node_id,
        "artifact_id": p1.get("artifact_id") or f"prd:{project_id}:{node_id}:{run_id}",
        "artifact_type": "prd",
        "generator": p1.get("generator") or "prd-generation",
        "created_at": getattr(args, "created_at", None) or p1.get("created_at") or datetime.now(timezone.utc).isoformat(),
    })
    if include_extended:
        p1.setdefault("schema_version", "2.0")
        p1.setdefault("generator_version", "2.0")
        p1.setdefault("input_artifacts", [])
    p1["requirement_ids"] = [item.get("id") for item in [
        *state.draft_content.get("P3", {}).get("functional", []),
        *state.draft_content.get("P3", {}).get("non_functional", []),
    ] if item.get("id")]
    return p1


def _quality_statistics(state: SessionState, review: dict | None = None) -> dict:
    """Compute report metrics from the structured PRD model, never Markdown."""
    requirements = state.draft_content.get("P3", {})
    functional = requirements.get("functional", [])
    non_functional = requirements.get("non_functional", [])
    all_items = [*functional, *non_functional]
    ledger = build_coverage_ledger(requirements, state.draft_content.get("P4", {}).get("contracts", []))
    ids = [item.get("id") for item in all_items if item.get("id")]
    known_ids = set(ids)
    contracts = state.draft_content.get("P4", {}).get("contracts", [])
    metrics = state.draft_content.get("P5", {}).get("metrics", [])
    referenced_ids = {
        str(reference)
        for item in [*contracts, *metrics]
        for reference in (item.get("verifies", []) if isinstance(item.get("verifies", []), list) else [item.get("verifies")])
        if reference and re.fullmatch(r"(?:REQ|NFR)-[A-Z0-9-]+", str(reference), re.IGNORECASE)
    }
    responses_by_contract: dict[str, set[tuple[str, ...]]] = {}
    for contract in contracts:
        contract_id = str(contract.get("id", ""))
        responses = contract.get("response", [])
        if isinstance(responses, str):
            responses = [responses]
        if contract_id:
            responses_by_contract.setdefault(contract_id, set()).add(tuple(map(str, responses)))
    conflicting_response_count = sum(
        len(responses) - 1 for responses in responses_by_contract.values() if len(responses) > 1
    )
    evidence_backed = sum(bool(item.get("evidence_refs")) for item in all_items)
    scopes = {scope: sum(item.get("release_scope", "current") == scope for item in all_items)
              for scope in ("current", "out_of_version", "not_applicable")}
    sources = {source: sum(item.get("source_kind") == source for item in all_items)
               for source in ("explicit", "valid_derivation")}
    current = [item for item in all_items if item.get("release_scope", "current") == "current"]
    return {
        "functional_requirement_count": len(functional), "nfr_count": len(non_functional),
        "release_scope_counts": scopes, "source_kind_counts": sources,
        "atomic_requirement_ratio": (sum(item.get("requirement_kind", "atomic") == "atomic" for item in current) / len(current)) if current else 0,
        "functional_oracle_coverage": sum(row["type"] == "functional" and row["status"] == "ready" for row in ledger),
        "nfr_verification_coverage": sum(row["type"] == "nfr" and row["status"] == "ready" for row in ledger),
        "ledger_counts": {status: sum(row["status"] == status for row in ledger) for status in ("ready", "blocked", "excluded")},
        "evidence_backed_requirement_count": evidence_backed,
        "evidence_coverage_ratio": evidence_backed / len(all_items) if all_items else 0,
        "unknown_reference_count": len(referenced_ids - known_ids), "duplicate_id_count": len(ids) - len(set(ids)),
        "conflicting_response_count": conflicting_response_count,
        "unconfirmed_assumption_count": sum(item.get("source_kind") in {"assumption", "unknown"} for item in all_items),
        "independent_review_finding_count": len((review or {}).get("findings", [])),
        "derive_parent_obligation_coverage": 1 if state.mode == "derive" and all_items else None,
        "derive_projection_used_count": sum("contract_projection:" in " ".join(contract.get("evidence_refs", [])) for contract in state.draft_content.get("P4", {}).get("contracts", [])),
        "derive_projection_failure_count": 0,
    }


def _structured_prd_model(state: SessionState) -> dict:
    """Expose the handoff schema and legacy phase containers from one model."""
    phases = state.draft_content
    p1, p3 = phases.get("P1", {}), phases.get("P3", {})
    return {
        **phases, **p1,
        "mode": state.mode,
        "problem_statement": phases.get("P2", {}),
        "functional_requirements": p3.get("functional", []),
        "non_functional_requirements": p3.get("non_functional", []),
        "architecture_input_contract": phases.get("P6", {}),
        "success_metrics": phases.get("P5", {}).get("metrics", []),
        "acceptance_contracts": phases.get("P4", {}).get("contracts", []),
        "oracle_coverage_ledger": build_coverage_ledger(p3, phases.get("P4", {}).get("contracts", [])),
        "future_backlog": [item for item in [*p3.get("functional", []), *p3.get("non_functional", [])]
                           if item.get("release_scope", "current") != "current"],
        "blocking_questions": [],
    }


def _write_root_sidecars(state: SessionState, prd_path: Path, errors: list[str], args: argparse.Namespace, *, status: str, review: dict | None = None) -> None:
    """Write machine-readable artifacts from the same in-memory PRD model."""
    root = prd_path.parent
    root.mkdir(parents=True, exist_ok=True)
    model = state.draft_content
    p1 = model.setdefault("P1", {})
    if status == "PASS":
        p1.setdefault("status", "complete" if state.mode == "derive" else "approved")
        p1.setdefault("ready_for_test_generation", True)
    else:
        p1["status"] = "draft"
        p1["ready_for_test_generation"] = False
    prd_text = prd_path.read_text(encoding="utf-8")
    identity = _artifact_identity(state, args)
    (root / "prd.json").write_text(json.dumps(_structured_prd_model(state), ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "prd_manifest.json").write_text(json.dumps({
        **identity, "schema_version": "2.0", "status": status, "handoff_status": status,
        "prd_file": prd_path.name,
        "prd_sha256": hashlib.sha256(prd_text.encode("utf-8")).hexdigest(),
        "input_artifacts": model.get("P1", {}).get("input_artifacts", []),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "status": status, "errors": errors,
        "oracle_blocked_count": len(_check_oracle_coverage(state)),
        "review": review or {"status": "pending"},
        "quality_statistics": _quality_statistics(state, review),
    }
    (root / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    log = {
        "run_id": identity["run_id"], "project_id": identity["project_id"], "node_id": identity["node_id"],
        "module": "prd-generation", "code_version": identity.get("generator_version", "unknown"),
        "schema_version": "2.0", "mode": state.mode, "start_time": now, "end_time": now, "duration_ms": 0,
        "status": status, "exit_code": 0 if status == "PASS" else EXIT_QUALITY_BLOCKED,
        "input_artifacts": identity.get("input_artifacts", []),
        "output_artifacts": [prd_path.name, "prd.json", "prd_manifest.json", "validation_report.json"],
        "input_hash": _canonical_hash(model), "output_hash": hashlib.sha256(prd_text.encode("utf-8")).hexdigest(),
        "model": getattr(args, "model", None), "model_parameters": getattr(args, "model_params", None),
        "random_seed": getattr(args, "seed", None), "retry_count": 0, "token_usage": None, "estimated_cost": None,
        "human_interventions": 0, "question_count": 0, "oracle_blocked_count": report["oracle_blocked_count"],
        "review_finding_count": report["quality_statistics"]["independent_review_finding_count"],
        "warning_count": 0, "error_type": None if status == "PASS" else "QUALITY_BLOCKED",
        "error_message": None if status == "PASS" else "; ".join(errors),
    }
    (root / "execution_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    if status != "PASS":
        (root / "blocking_questions.json").write_text(json.dumps({"status": "blocked", "questions": errors}, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_review(review_path: str | None, input_hash: str) -> tuple[bool, dict, list[str]]:
    """Accept only a separately produced, input-bound review artifact."""
    if not review_path:
        return False, {"status": "pending"}, ["REVIEW_PENDING: an independent review artifact is required."]
    try:
        review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, {"status": "invalid"}, [f"REVIEW_PENDING: cannot load review artifact: {exc}"]
    required = ("input_hash", "reviewer", "reviewed_at", "status", "findings")
    if any(key not in review for key in required) or review.get("input_hash") != input_hash:
        return False, review, ["REVIEW_PENDING: review artifact is incomplete or targets different input."]
    if review.get("status") != "passed" or review.get("findings"):
        return False, review, ["REVIEW_FAILED: independent review has findings or did not pass."]
    return True, review, []


def _write_error_report(state: SessionState, errors: list, args: argparse.Namespace) -> None:
    """Write draft PRD and JSON error report on quality failure."""
    if state.mode == "derive":
        print("\n[ERROR] Derive failed:")
        for error in errors:
            print(f"  - {error}")
        return

    # A blocked Root run is always a draft; a normal .md cannot mask failure.
    p1 = state.draft_content.setdefault("P1", {})
    p1.update({"status": "draft", "release_scope_frozen": False,
               "ready_for_test_generation": False, "agent_review_passed": False})
    _artifact_identity(state, args)
    prd_text = assemble_prd(state.draft_content)
    parent_doc = state.draft_content.get("P1", {}).get("parent_doc", "unknown")
    module_name = state.draft_content.get("P1", {}).get("module_name", "unknown")
    version = state.draft_content.get("P1", {}).get("version", "1.0.0")
    draft_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name}_prd_v{version}.md")
    if not draft_path.name.endswith(".draft.md"):
        draft_path = draft_path.with_suffix(".draft.md")
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(prd_text, encoding="utf-8")

    # Write JSON error report to .draft.errors.json
    errors_path = draft_path.with_suffix(".errors.json")
    errors_path.write_text(
        json.dumps({"errors": errors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_root_sidecars(state, draft_path, errors, args, status="FAIL")

    print(f"\n草稿PRD已保存至: {draft_path}")
    print(f"错误报告已保存至: {errors_path}")


def _resume_session(session_path: Path, args: argparse.Namespace) -> None:
    """从会话文件恢复并继续流程。"""
    state = load_session(session_path)
    print(f"恢复会话: {state.session_id}, 模式: {state.mode}")

    phase_order = [
        ("P1", FrontmatterPhase),
        ("P2", ProblemStatementPhase),
        ("P3", RequirementsPhase),
        ("P5", SuccessMetricsPhase),
        ("P4", AcceptancePhase),
    ]

    for phase_id, PhaseClass in phase_order:
        if phase_id in state.completed_phases:
            # Print brief summary
            data = state.draft_content.get(phase_id, {})
            if phase_id == "P1":
                print(f"[{phase_id}] 已完成 - 文档ID: {data.get('doc_id', 'N/A')}")
            elif phase_id == "P2":
                pain_points = data.get("pain_points", "")
                summary = pain_points[:30] + "..." if len(pain_points) > 30 else pain_points
                print(f"[{phase_id}] 已完成 - 目标用户: {data.get('target_users', 'N/A')}, 痛点: {summary}")
            elif phase_id == "P3":
                functional = data.get("functional", [])
                print(f"[{phase_id}] 已完成 - 功能需求: {len(functional)} 条")
            elif phase_id == "P4":
                contracts = data.get("contracts", [])
                print(f"[{phase_id}] 已完成 - Acceptance Contracts: {len(contracts)} 个")
            elif phase_id == "P5":
                metrics = data.get("metrics", [])
                print(f"[{phase_id}] 已完成 - 成功指标: {len(metrics)} 个")

            if _ask_continue("是否要修改此阶段"):
                phase = PhaseClass(state)
                phase.run()
        else:
            print(f"[{phase_id}] 未完成，继续执行...")
            phase = PhaseClass(state)
            phase.run()

    oracle_gaps = _check_oracle_coverage(state)
    if oracle_gaps:
        errors = [f"[{gap['id']}] {gap['reason']}" for gap in oracle_gaps]
        _write_error_report(state, errors, args)
        print("[ERROR] 当前版本需求存在缺失判定依据，PRD 未进入 ready 状态。")
        return EXIT_QUALITY_BLOCKED

    # Final assembly
    prd_text = assemble_prd(state.draft_content)

    # Quality gate after P3 (if P3 was completed or just run)
    smart_results = _run_smart_check(state)
    report = format_quality_report(smart_results=smart_results)
    print(report)

    if not all(r.overall_pass for r in smart_results):
        print("\n[WARNING]  发现质量问题，建议修复后重新收集需求。")
        # Print fix suggestions for failed items
        functional = state.draft_content.get("P3", {}).get("functional", [])
        for result in smart_results:
            if not result.overall_pass:
                req = next((r for r in functional if r.get("id") == result.req_id), {})
                fix = suggest_fix(req, result)
                print(f"  [HINT] [{result.req_id}] {fix}")
        if not _ask_continue("是否继续生成PRD"):
            print("已取消。可重新运行工具修正需求。")
            return

    # Final quality gate (ambiguity scan)
    ambiguity = _run_ambiguity_check(state, prd_text)
    if ambiguity["lexical"] or ambiguity["logic"] or ambiguity["completeness"]:
        report = format_quality_report(smart_results=[], ambiguity_result=ambiguity)
        print(report)
        if not _ask_continue("是否继续生成最终PRD"):
            print("已取消。可重新运行工具修正内容。")
            return

    # A resumed flow must obey the same review, status, and sidecar contract
    # as a fresh Root/Derive run.
    _artifact_identity(state, args)
    review: dict | None = None
    if state.mode == "root":
        input_hash = _canonical_hash(state.draft_content)
        review_ok, review, review_errors = _load_review(
            getattr(args, "review_artifact", None), input_hash
        )
        if not review_ok:
            _write_error_report(state, review_errors, args)
            return EXIT_QUALITY_BLOCKED
        state.draft_content["P1"].update({
            "status": "approved", "release_scope_frozen": True,
            "agent_review_passed": True, "ready_for_test_generation": True,
            "review_input_hash": input_hash,
        })
    else:
        state.draft_content.setdefault("P1", {}).setdefault("status", "complete")
    prd_text = assemble_prd(state.draft_content)

    # Save PRD to file
    if state.mode == "derive":
        parent_doc = state.draft_content["P1"].get("parent_doc", "unknown")
        module_name = state.draft_content["P1"].get("module_name", "unknown")
        version = state.draft_content["P1"].get("version", "1.0.0")
        output_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name}_prd_v{version}.md")
    else:
        project_name = state.draft_content["P1"].get("project_name", "unknown")
        version = state.draft_content["P1"].get("version", "1.0.0")
        output_path = Path(args.output) if args.output else Path(f"{project_name}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    _write_root_sidecars(
        state, output_path, [], args, status="PASS",
        review=review or {"status": "inheritance_allocation_gate", "findings": []},
    )
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    new_session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, new_session_path)
    print(f"会话已保存至: {new_session_path}")


def run_root_mode(args: argparse.Namespace) -> None:
    """Run PRD generation in Root mode."""
    print("=" * 50)
    print("PRD Flow - Root Mode")
    print("=" * 50)

    state = SessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )

    # Phase 1: Frontmatter
    phase1 = FrontmatterPhase(state)
    phase1.run()
    print(f"\n生成文档ID: {state.draft_content['P1']['doc_id']}")

    # Phase 2: Problem Statement
    phase2 = ProblemStatementPhase(state)
    phase2.run()

    # Phase 3: Requirements (with quality gate)
    phase3 = RequirementsPhase(state)
    phase3.run()

    # Quality gate after P3
    smart_results = _run_smart_check(state)
    report = format_quality_report(smart_results=smart_results)
    print(report)

    if not all(r.overall_pass for r in smart_results):
        print("\n[WARNING]  发现质量问题，建议修复后重新收集需求。")
        # Print fix suggestions for failed items
        functional = state.draft_content.get("P3", {}).get("functional", [])
        for result in smart_results:
            if not result.overall_pass:
                req = next((r for r in functional if r.get("id") == result.req_id), {})
                fix = suggest_fix(req, result)
                print(f"  [HINT] [{result.req_id}] {fix}")
        if not _ask_continue("是否继续生成PRD"):
            print("已取消。可重新运行工具修正需求。")
            return

    # Define metrics before the acceptance contracts that verify them.
    phase5 = SuccessMetricsPhase(state)
    phase5.run()

    # Phase 4 stores business oracles for downstream test generation.
    phase4 = AcceptancePhase(state)
    phase4.run()

    coverage_gaps = _check_oracle_coverage(state)
    if coverage_gaps:
        errors = [f"[{gap['id']}] {gap['reason']}" for gap in coverage_gaps]
        _write_error_report(state, errors, args)
        print("\n[ERROR] 当前版本需求存在缺失判定依据，PRD 未进入 ready 状态。")
        return EXIT_QUALITY_BLOCKED

    # Final assembly
    prd_text = assemble_prd(state.draft_content)

    # Final quality gate (ambiguity scan)
    ambiguity = _run_ambiguity_check(state, prd_text)
    if ambiguity["lexical"] or ambiguity["logic"] or ambiguity["completeness"]:
        report = format_quality_report(smart_results=[], ambiguity_result=ambiguity)
        print(report)
        if not _ask_continue("是否继续生成最终PRD"):
            print("已取消。可重新运行工具修正内容。")
            return

    # A Root artifact becomes handoff-ready only after a separately produced,
    # input-bound review.  Interactive generation is therefore safe by default:
    # without --review-artifact it emits a draft and exits as quality-blocked.
    input_hash = _canonical_hash(state.draft_content)
    review_ok, review, review_errors = _load_review(
        getattr(args, "review_artifact", None), input_hash
    )
    if not review_ok:
        _write_error_report(state, review_errors, args)
        return EXIT_QUALITY_BLOCKED
    state.draft_content["P1"].update({
        "status": "approved", "release_scope_frozen": True,
        "agent_review_passed": True, "ready_for_test_generation": True,
        "review_input_hash": input_hash,
    })
    _artifact_identity(state, args)
    prd_text = assemble_prd(state.draft_content)

    # Save PRD to file
    project_name = state.draft_content["P1"].get("project_name", "unknown")
    version = state.draft_content["P1"].get("version", "1.0.0")
    output_path = Path(args.output) if args.output else Path(f"{project_name}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    _write_root_sidecars(state, output_path, [], args, status="PASS", review=review)
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"会话已保存至: {session_path}")


def _read_structured_input(path: str) -> dict:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"INPUT_ENCODING_ERROR: {source}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"INPUT_FILE_ERROR: {source}: {exc}") from exc
    try:
        payload = json.loads(text) if source.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"INPUT_PARSE_ERROR: {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaIncompatibleError("INPUT_SCHEMA_ERROR: Root input must be a JSON/YAML object.")
    p1 = payload.get("P1") or payload.get("frontmatter") or {}
    if p1 is not None and not isinstance(p1, dict):
        raise SchemaIncompatibleError("INPUT_SCHEMA_ERROR: P1/frontmatter must be an object.")
    schema_version = payload.get("schema_version") or p1.get("schema_version")
    if schema_version is not None and str(schema_version) != "2.0":
        raise SchemaIncompatibleError(
            f"SCHEMA_INCOMPATIBLE: expected PRD schema_version 2.0, got {schema_version}."
        )
    artifact_type = payload.get("artifact_type") or p1.get("artifact_type")
    if artifact_type is not None and artifact_type != "prd":
        raise SchemaIncompatibleError(
            f"SCHEMA_INCOMPATIBLE: expected artifact_type prd, got {artifact_type}."
        )
    for canonical, alias in (("P2", "problem_statement"), ("P3", "requirements"),
                             ("P4", "acceptance"), ("P5", "success_metrics"),
                             ("P6", "architecture_input")):
        section = payload.get(canonical, payload.get(alias, {}))
        if section is not None and not isinstance(section, dict):
            raise SchemaIncompatibleError(
                f"INPUT_SCHEMA_ERROR: {canonical}/{alias} must be an object."
            )
    requirements = payload.get("P3") or payload.get("requirements") or {}
    for field in ("functional", "non_functional"):
        value = requirements.get(field)
        if value is not None and not isinstance(value, list):
            raise SchemaIncompatibleError(
                f"INPUT_SCHEMA_ERROR: P3.{field} must be a list."
            )
    return payload


def run_root_noninteractive(args: argparse.Namespace) -> int:
    """Generate a Root artifact without calling input(), for reproducible runs."""
    try:
        payload = _read_structured_input(args.input)
    except SchemaIncompatibleError as exc:
        print(str(exc))
        return EXIT_SCHEMA_INCOMPATIBLE
    except ValueError as exc:
        print(str(exc))
        return EXIT_INPUT_ERROR
    p1 = dict(payload.get("P1") or payload.get("frontmatter") or {})
    p2 = dict(payload.get("P2") or payload.get("problem_statement") or {})
    p3 = dict(payload.get("P3") or payload.get("requirements") or {})
    p4 = dict(payload.get("P4") or payload.get("acceptance") or {})
    p5 = dict(payload.get("P5") or payload.get("success_metrics") or {})
    p6 = dict(payload.get("P6") or payload.get("architecture_input") or {})
    p1.pop("agent_review_passed", None)  # caller-controlled booleans are not review evidence
    p1.setdefault("doc_id", p1.get("project_id", "root-prd"))
    p3.setdefault("functional", [])
    p3.setdefault("non_functional", [])
    p4.setdefault("contracts", [])
    p5.setdefault("metrics", [])
    state = SessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}", mode="root", current_phase="complete",
        completed_phases=["P1", "P2", "P3", "P4", "P5"],
        draft_content={"P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5, "P6": p6},
    )
    _artifact_identity(state, args, include_extended=False)
    gaps = _check_oracle_coverage(state)
    errors = [f"[{gap['id']}] {gap['reason']}" for gap in gaps]
    if not p3["functional"] and not p3["non_functional"]:
        errors.append("INPUT_INCOMPLETE: at least one requirement is required.")
    input_hash = _canonical_hash(state.draft_content)
    review_ok, review, review_errors = _load_review(getattr(args, "review_artifact", None), input_hash)
    errors.extend(review_errors)
    output_root = Path(args.output_dir or args.output or ".")
    if output_root.suffix:
        draft_path = output_root.with_name(output_root.stem + ".draft.md")
        ready_path = output_root
    else:
        draft_path = output_root / "prd.draft.md"
        ready_path = output_root / "prd.md"
    if errors or getattr(args, "validate_only", False):
        _write_error_report(state, errors or ["VALIDATE_ONLY"], argparse.Namespace(**{**vars(args), "output": str(draft_path)}))
        return EXIT_QUALITY_BLOCKED
    p1.update({"status": "approved", "release_scope_frozen": True, "agent_review_passed": True,
               "ready_for_test_generation": True, "review_input_hash": input_hash})
    _artifact_identity(state, args)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_text(assemble_prd(state.draft_content), encoding="utf-8")
    _write_root_sidecars(state, ready_path, [], args, status="PASS", review=review)
    return EXIT_SUCCESS


def run_derive_mode(args: argparse.Namespace) -> int:
    """Run PRD generation in Derive mode (fully automated, no input() calls)."""
    print("=" * 50)
    print("PRD Flow - Derive Mode")
    print("=" * 50)

    # 1. Validate inputs
    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    target_granularity = getattr(args, "target_granularity", "auto") or "auto"
    if not args.parent_prd or not architecture_input or not args.target_module:
        print("Error: Derive mode requires --parent-prd, --architecture-package, and --target-module")
        return EXIT_INPUT_ERROR

    print(f"\nTarget module: {args.target_module}")
    print(f"Target granularity: {target_granularity}")
    print(f"Parent PRD: {args.parent_prd}")
    print(f"Architecture package: {architecture_input}")

    # 2. Parse parent documents
    target_module = args.target_module
    try:
        context = build_derive_context(
            Path(args.parent_prd),
            Path(architecture_input),
            target_module,
            target_granularity=target_granularity,
        )
    except FileNotFoundError:
        print(f"INPUT_FILE_ERROR: parent PRD not found: {args.parent_prd}")
        return EXIT_INPUT_ERROR
    except UnicodeDecodeError as exc:
        print(f"INPUT_ENCODING_ERROR: {exc}")
        return EXIT_DEPENDENCY_ERROR

    # 3. Auto-fix module name via edit distance matching
    if not context["success"]:
        similar = find_best_module_match(target_module, context.get("available_modules", []))
        if similar:
            target_module = similar
            context = build_derive_context(
                Path(args.parent_prd),
                Path(architecture_input),
                target_module,
                target_granularity=target_granularity,
            )
        if not context["success"]:
            print(context["error"])
            print("可用模块:")
            for mod in context.get("available_modules", []):
                print(f"  - {mod}")
            return EXIT_INPUT_ERROR

    module_name = context["module_name"]
    related_requirements = context.get("related_requirements", [])
    authoritative_requirements = _authoritative_derive_requirements(related_requirements)
    interfaces = context.get("interfaces", [])
    actionable_interfaces: list[dict] = []
    dependencies = context.get("dependencies", [])
    events: list[dict] = []
    external_dependencies: list[dict] = []
    data_assets: list[dict] = []
    related_acceptance_contracts = context.get("related_acceptance_contracts", [])
    related_non_functional = context.get("related_non_functional", [])
    related_success_metrics = context.get("related_success_metrics", [])
    implementation_surfaces = context.get("implementation_surfaces", [])

    # 4. Keep a transparent parent-coverage ledger without blocking this target.
    orphan_requirements = context.get("orphan_requirements", [])
    derive_warnings = list(
        context.get("derive_warnings", context.get("coverage_gaps", []))
    )
    derive_warnings.extend(
        f"Parent requirement {req.get('id', 'UNKNOWN')} has no owner at the selected derive granularity."
        for req in orphan_requirements
    )
    derive_warnings = list(dict.fromkeys(derive_warnings))
    coverage_ledger = list(context.get("coverage_ledger", []))
    if not coverage_ledger:
        coverage_ledger.extend(
            {
                "id": req.get("id", "UNKNOWN"),
                "kind": "requirement",
                "owners": [module_name],
                "status": "inherited_by_target",
            }
            for req in related_requirements
        )
        coverage_ledger.extend(
            {
                "id": req.get("id", "UNKNOWN"),
                "kind": "requirement",
                "owners": [],
                "status": "unassigned",
            }
            for req in orphan_requirements
        )
    coverage_complete = bool(coverage_ledger) and all(
        item.get("status") != "unassigned" for item in coverage_ledger
    )

    # 5. Log summary (no user confirmation needed)
    print(f"\n模块: {module_name}")
    print(f"相关需求: {len(related_requirements)} 条")
    print(f"接口: {len(interfaces)} 个")
    print(f"事件契约: {len(events)} 个")
    print(f"依赖: {len(dependencies)} 个")
    print(f"实现面: {', '.join(implementation_surfaces) if implementation_surfaces else 'domain_logic'}")
    print(
        "父需求分发: "
        + ("完整" if coverage_complete else "存在尚未分配项，详见覆盖账本")
    )

    # 6. Initialize SessionState
    state = SessionState(
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
        mode="derive",
        current_phase="D1",
        completed_phases=[],
        draft_content={},
        parent_context=context,
        target_module=target_module,
    )

    # D1: Frontmatter — auto-generate
    phase1 = FrontmatterPhase(state)
    phase1.collect_derive(
        parent_doc_id=context["parent_doc_id"],
        parent_arch_id=context.get("parent_arch_id"),
        module_name=module_name,
        interfaces=interfaces,
        dependencies=dependencies,
        events=events,
        implementation_surfaces=implementation_surfaces,
        priority="P0",
        author="Claude",
    )
    print(f"\n生成文档ID: {state.draft_content['P1']['doc_id']}")

    if derive_warnings:
        print("\n[WARNING] 派生覆盖提示（不阻断当前目标生成）:")
        for warning in derive_warnings:
            print(f"  - {warning}")

    # Helper: clean requirement text (take first line only, strip markdown)
    def _clean_req_text(text: str) -> str:
        return text.split("\n")[0].strip().rstrip("-").strip()

    # D2: Problem Statement — auto-prefill from module context
    phase2 = ProblemStatementPhase(state)
    target_users = "该模块的上游调用方和受其行为影响的系统用户"
    module_responsibility = ""
    if isinstance(context.get("module"), dict):
        module_responsibility = context["module"].get("responsibility", "")
    if authoritative_requirements:
        first_req_text = _clean_req_text(authoritative_requirements[0].get("text", ""))
        pain_points = f"上层节点中与 {module_name} 相关的行为需要被收窄到该模块边界内：{first_req_text}"
    else:
        pain_points = f"上层架构已定义 {module_name} 边界，但父 PRD 中未找到可安全归属到该模块的需求"
    opportunity = (
        f"由 {module_name} 只承接自身拥有的行为"
        + (f"（{module_responsibility}）" if module_responsibility else "")
        + "，避免把父层复杂度平移到子 PRD。"
    )
    phase2.collect(target_users=target_users, pain_points=pain_points, opportunity=opportunity)

    # D3: Requirements — one focused child requirement per owned parent requirement
    phase3 = RequirementsPhase(state)
    functional = []
    parent_to_child: dict[str, str] = {}
    used_derived_ids: set[str] = set()
    for req in authoritative_requirements:
        req_id = req.get("id", "REQ-UNKNOWN")
        req_text = _clean_req_text(req.get("text", ""))
        parent_priority = req.get("priority", "Must Have")
        child_id = _derived_requirement_id("REQ", req_id, used_derived_ids)
        parent_to_child[req_id] = child_id
        child_req = {
            "id": child_id,
            "text": req_text,
            "priority": parent_priority,
            "release_scope": req.get("release_scope", "current"),
            "scope_reason": req.get("scope_reason", ""),
            "requirement_kind": "atomic",
            "parent_req": req_id,
            "source_kind": "parent_requirement",
            "evidence_refs": list(dict.fromkeys([
                *req.get("evidence_refs", []),
                f"parent_requirement:{req_id}",
            ])),
            "implementation_surfaces": context.get("requirement_surfaces", {}).get(
                req_id,
                ["domain_logic"],
            ),
        }
        functional.append(child_req)

    # Architecture is recorded only as non-normative references; it cannot create product requirements.
    non_functional = []
    parent_nfr_to_child: dict[str, str] = {}
    for nfr in related_non_functional:
        parent_nfr_id = nfr.get("id", "NFR-UNKNOWN")
        child_nfr_id = _derived_requirement_id("NFR", parent_nfr_id, used_derived_ids)
        parent_nfr_to_child[parent_nfr_id] = child_nfr_id
        non_functional.append(
            {
                "id": child_nfr_id,
                "text": _clean_req_text(nfr.get("text", "")),
                "parent_nfr": nfr.get("id", "NFR-UNKNOWN"),
                "source_kind": "parent_requirement",
                "evidence_refs": list(dict.fromkeys([
                    *nfr.get("evidence_refs", []),
                    f"parent_requirement:{nfr.get('id', 'NFR-UNKNOWN')}",
                ])),
            }
        )
    phase3.collect(functional=functional, non_functional=non_functional)
    state.draft_content["P1"]["requirement_id_mapping"] = {
        **parent_to_child,
        **parent_nfr_to_child,
    }
    state.draft_content["P3"]["non_goals"] = list(context.get("non_goals", []))

    derive_gate_errors: list[str] = []
    current_requirements = [
        requirement
        for requirement in [*functional, *non_functional]
        if requirement.get("release_scope", "current") == "current"
    ]
    if not current_requirements:
        derive_gate_errors.append(
            f"Target module {module_name} has no inherited current-release requirement."
        )
    traceability_result = check_parent_traceability(functional)
    if not traceability_result.passed:
        derive_gate_errors.extend(traceability_result.errors)
    if derive_gate_errors:
        _write_error_report(state, derive_gate_errors, args)
        return EXIT_QUALITY_BLOCKED

    # D4: preserve explicit parent Acceptance Contracts only.
    phase4 = AcceptancePhase(state)
    derived_contracts: list[dict] = []
    contract_projection_errors: list[str] = []
    contract_projections = _load_contract_projections(
        getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", "")
    )
    parent_reference_mapping = {**parent_to_child, **parent_nfr_to_child}
    parent_requirement_records = [*authoritative_requirements, *related_non_functional]
    for parent_contract in related_acceptance_contracts:
        verifies = parent_contract.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        projection = contract_projections.get(
            (module_name, parent_contract.get("id", ""))
        )
        additional_verifies = projection.get("legacy_additional_verifies", []) if projection else []
        if isinstance(additional_verifies, str):
            additional_verifies = [additional_verifies]
        effective_verifies = list(dict.fromkeys([*verifies, *additional_verifies]))
        mapped = _map_parent_references(
            effective_verifies,
            parent_requirement_records,
            parent_reference_mapping,
        )
        if not mapped:
            continue
        mapped_parent_refs = [
            reference
            for reference in effective_verifies
            if _map_parent_references(
                [reference], parent_requirement_records, parent_reference_mapping
            )
        ]
        if len(mapped_parent_refs) < len(effective_verifies) and not projection:
            contract_projection_errors.append(
                f"Partial parent contract {parent_contract.get('id', 'UNKNOWN')} for {module_name} "
                "requires acceptance-contract-projections.yaml."
            )
            continue
        contract = _normalize_inherited_contract_pairs(parent_contract)
        parent_contract_id = parent_contract.get("id", "AC-UNKNOWN")
        contract["id"] = (
            parent_contract_id
            if re.match(r"^D+-AC-", parent_contract_id, re.IGNORECASE)
            else f"D-{parent_contract_id}"
        )
        contract["verifies"] = mapped
        if projection:
            mode = projection.get("mode")
            if mode == "project":
                contract.update(projection.get("contract", {}))
                contract["verifies"] = mapped
            elif mode != "shared":
                contract_projection_errors.append(
                    f"Invalid projection mode for {module_name}/{parent_contract_id}: {mode}"
                )
                continue
        evidence = parent_contract.get("evidence_refs", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        projection_evidence = (
            [f"contract_projection:{module_name}:{projection.get('mode')}"]
            if projection else []
        )
        contract["evidence_refs"] = list(dict.fromkeys([
            *evidence,
            f"parent_acceptance_contract:{parent_contract.get('id', 'UNKNOWN')}",
            *projection_evidence,
        ]))
        derived_contracts.append(contract)
    if contract_projection_errors:
        _write_error_report(state, contract_projection_errors, args)
        return EXIT_QUALITY_BLOCKED
    phase4.collect(contracts=derived_contracts)

    oracle_gaps = _check_oracle_coverage(state)
    if oracle_gaps:
        errors = [f"[{gap['id']}] {gap['reason']}" for gap in oracle_gaps]
        _write_error_report(state, errors, args)
        print("[ERROR] Derive lost one or more inherited Acceptance Contracts.")
        return EXIT_QUALITY_BLOCKED

    # D5: preserve source-defined metrics. NFR contracts carry authoritative
    # population/window/unit/threshold/exclusion/pass-rule definitions.
    phase5 = SuccessMetricsPhase(state)
    metrics = []
    metric_errors: list[str] = []
    for index, metric in enumerate(context.get("related_success_metrics", []), start=1):
        normalized = dict(metric)
        normalized.setdefault("id", f"METRIC-D{index:03d}")
        verifies = normalized.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        requirement_refs = [
            reference
            for reference in verifies
            if re.fullmatch(r"(?:REQ|NFR)-[A-Z0-9-]+", reference, re.IGNORECASE)
        ]
        mapped_refs = _map_parent_references(
            requirement_refs,
            parent_requirement_records,
            parent_reference_mapping,
        )
        if requirement_refs and not mapped_refs:
            metric_errors.append(
                f"Success metric {normalized['id']} has no requirement in target module {module_name}."
            )
            continue
        non_requirement_refs = [reference for reference in verifies if reference not in requirement_refs]
        normalized["verifies"] = [*mapped_refs, *non_requirement_refs]
        metrics.append(normalized)
    if metric_errors:
        _write_error_report(state, metric_errors, args)
        return EXIT_QUALITY_BLOCKED
    phase5.collect(metrics=metrics)

    _artifact_identity(state, args)
    prd_text = assemble_prd(state.draft_content)
    if args.output:
        output_path = Path(args.output)
    elif getattr(args, "output_dir", None):
        output_path = _derive_all_destinations(
            Path(args.parent_prd),
            Path(args.output_dir),
            [module_name],
        )[module_name] / "prd.md"
    else:
        output_path = Path(f"{context['parent_doc_id']}_{module_name}_prd_v1.0.0.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prd_text, encoding="utf-8")
    _write_root_sidecars(
        state, output_path, [], args, status="PASS",
        review={"status": "inheritance_allocation_gate", "findings": []},
    )
    print(f"\nPRD已保存至: {output_path}")
    return EXIT_SUCCESS


def _module_slug(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name)
    return "-".join(part for part in slug.split("-") if part)


def _parent_layer(parent_prd: Path) -> int | None:
    for part in reversed(parent_prd.parts):
        match = re.match(r"^L(\d+)(?:-|$)", part, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _parent_module_name(parent_prd: Path) -> str:
    try:
        frontmatter = parse_parent_prd(parent_prd).get("frontmatter", {})
    except (OSError, ValueError):
        frontmatter = {}
    module_name = frontmatter.get("module_name") if isinstance(frontmatter, dict) else None
    if module_name:
        return str(module_name)
    return re.sub(r"^L\d+-", "", parent_prd.parent.name, flags=re.IGNORECASE)


def _module_abbreviation(module_name: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", module_name)
    explicit_acronyms = [token for token in tokens if len(token) > 1 and token.isupper()]
    if explicit_acronyms:
        return explicit_acronyms[-1].lower()
    abbreviation = "".join(token[0].lower() for token in tokens if token)
    return abbreviation or "parent"


def _is_word_abbreviation(candidate: str, word: str) -> bool:
    iterator = iter(word.lower())
    return bool(candidate) and all(any(char == current for current in iterator) for char in candidate.lower())


def _child_module_slugs(module_names: list[str], parent_name: str, parent_abbreviation: str) -> dict[str, str]:
    slugs = {
        module_name: re.sub(r"^l\d+-", "", _module_slug(module_name), flags=re.IGNORECASE)
        for module_name in module_names
    }
    parent_tokens = _module_slug(parent_name).split("-")
    for module_name, slug in list(slugs.items()):
        tokens = slug.split("-")
        if tokens[:len(parent_tokens)] == parent_tokens and len(tokens) > len(parent_tokens):
            slugs[module_name] = "-".join(tokens[len(parent_tokens):])
        elif len(tokens) > 1 and (
            tokens[0] == parent_abbreviation
            or any(_is_word_abbreviation(tokens[0], word) for word in parent_tokens)
        ):
            slugs[module_name] = "-".join(tokens[1:])

    token_lists = [slug.split("-") for slug in slugs.values()]
    common: list[str] = []
    if token_lists:
        for tokens in zip(*token_lists):
            if len(set(tokens)) != 1:
                break
            common.append(tokens[0])

    parent_slug = _module_slug(parent_name)
    common_slug = "-".join(common)
    parent_words = parent_slug.split("-")
    common_is_parent_namespace = bool(common) and (
        common_slug == parent_abbreviation
        or parent_slug.startswith(f"{common_slug}-")
        or parent_slug.endswith(f"-{common_slug}")
        or common_slug == parent_slug
        or (len(common) == 1 and any(_is_word_abbreviation(common[0], word) for word in parent_words))
    )
    if common_is_parent_namespace and all(len(tokens) > len(common) for tokens in token_lists):
        return {
            module_name: "-".join(slug.split("-")[len(common):])
            for module_name, slug in slugs.items()
        }
    return slugs


def _derive_all_destinations(
    parent_prd: Path,
    output_root: Path,
    module_names: list[str],
) -> dict[str, Path]:
    parent_level = _parent_layer(parent_prd)
    if parent_level is None:
        return {module_name: output_root / f"L1-{_module_slug(module_name)}" for module_name in module_names}

    child_level = parent_level + 1
    layer_name = f"L{child_level}"
    if child_level == 1:
        return {
            module_name: output_root / layer_name / f"{layer_name}-{_module_slug(module_name)}"
            for module_name in module_names
        }

    parent_name = _parent_module_name(parent_prd)
    parent_abbreviation = _module_abbreviation(parent_name)
    child_slugs = _child_module_slugs(module_names, parent_name, parent_abbreviation)
    return {
        module_name: output_root
        / layer_name
        / parent_abbreviation
        / f"{layer_name}-{parent_abbreviation}-{child_slugs[module_name]}"
        for module_name in module_names
    }


def run_derive_all_mode(args: argparse.Namespace) -> int:
    """Allocate the complete parent scope, then generate every direct child PRD."""
    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    output_dir = Path(args.output_dir)
    allocation = build_layer_allocation(
        Path(args.parent_prd),
        Path(architecture_input),
        target_granularity=args.target_granularity,
    )
    allocation_report = getattr(args, "allocation_report", None)
    if allocation_report:
        report_path = Path(allocation_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {key: value for key, value in allocation.items() if key != "contexts"},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    if not allocation.get("success"):
        print("[ERROR] Full-layer allocation is incomplete; no child PRD was generated.")
        for error in allocation.get("errors", []):
            print(f"  - {error}")
        return EXIT_QUALITY_BLOCKED

    destinations = _derive_all_destinations(
        Path(args.parent_prd),
        output_dir,
        allocation["target_modules"],
    )
    staged: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="prd-derive-") as temporary_root:
        temporary_root_path = Path(temporary_root)
        for module_name in allocation["target_modules"]:
            child_dir_name = destinations[module_name].name
            staged_path = temporary_root_path / child_dir_name / "prd.md"
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            child_args = argparse.Namespace(**vars(args))
            child_args.target_module = module_name
            child_args.output = str(staged_path)
            result = run_derive_mode(child_args)
            if result != EXIT_SUCCESS:
                print("[ERROR] Full-layer Derive failed; existing outputs were not changed.")
                return EXIT_QUALITY_BLOCKED
            staged.append({
                "module": module_name,
                "directory": destinations[module_name],
                "path": staged_path,
            })

        output_dir.mkdir(parents=True, exist_ok=True)
        for item in staged:
            child_dir = item["directory"]
            child_dir.mkdir(parents=True, exist_ok=True)
            (child_dir / "prd.md").write_text(
                item["path"].read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            for legacy_name in ("prd.draft.md", "prd.draft.errors.json"):
                legacy_path = child_dir / legacy_name
                if legacy_path.exists():
                    legacy_path.unlink()

    return EXIT_SUCCESS


def _select_mode_interactive(args: argparse.Namespace) -> Mode:
    """交互式选择运行模式。如果命令行已提供derive参数则自动推断。"""
    # Shortcut: all derive inputs present -> skip question
    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    if args.parent_prd and architecture_input and (args.target_module or getattr(args, "derive_all", False)):
        return Mode.DERIVE

    print("=" * 50)
    print("PRD Flow - 产品需求文档生成工具")
    print("=" * 50)
    print("\n请选择模式:")
    print("  [1] Root 模式 — 从零创建新的顶层 PRD")
    print("  [2] Derive 模式 — 基于已有 PRD 派生模块级 PRD")

    while True:
        choice = input("\n请输入 (1/2): ").strip()
        if choice == "1":
            return Mode.ROOT
        elif choice == "2":
            return Mode.DERIVE
        else:
            print("[WARNING]  无效输入，请输入 1 或 2")


def _prompt_derive_inputs(args: argparse.Namespace) -> argparse.Namespace:
    """Derive 模式下交互式补全缺失的输入参数。"""
    print("\n--- Derive 模式配置 ---")

    if not args.parent_prd:
        args.parent_prd = input("父 PRD 文件路径: ").strip()
    else:
        print(f"父 PRD 文件路径: {args.parent_prd}")

    architecture_input = getattr(args, "architecture_package", None) or getattr(args, "parent_architecture", None)
    if not architecture_input:
        args.architecture_package = input("架构包路径（目录、README.md 或 zip）: ").strip()
    else:
        print(f"架构包路径: {architecture_input}")

    if not args.target_module:
        args.target_module = input("目标模块名称: ").strip()
    else:
        print(f"目标模块名称: {args.target_module}")

    if not args.output and getattr(args, "output_dir", None):
        print(f"输出产品根目录: {args.output_dir}（自动推断层级目录）")
    elif not args.output:
        default_output = f"{args.target_module}_prd.md"
        out = input(f"输出文件路径 [默认: {default_output}]: ").strip()
        args.output = out if out else default_output
    else:
        print(f"输出文件路径: {args.output}")

    return args


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="PRD Flow - Interactive PRD generation")
    parser.add_argument("--input", help="JSON/YAML evidence and product-decision input for non-interactive Root mode")
    parser.add_argument("--parent-prd", help="Path to parent PRD document")
    parser.add_argument("--architecture-package", help="Path to architecture package directory, README.md, or zip")
    parser.add_argument("--parent-architecture", help="Legacy alias for --architecture-package")
    parser.add_argument("--target-module", help="Target module name for Derive mode")
    parser.add_argument("--derive-all", action="store_true", help="Allocate and generate every direct child module")
    parser.add_argument(
        "--output-dir",
        help="Product output root for layered Derive output; layer and parent-module directories are inferred",
    )
    parser.add_argument(
        "--allocation-report",
        help="Optional diagnostic JSON path for the full-layer allocation ledger",
    )
    parser.add_argument(
        "--target-granularity",
        choices=["auto", "deployable_module", "bounded_context", "component"],
        default="auto",
        help="Target level for Derive mode",
    )
    parser.add_argument("--resume", help="Path to session file to resume")
    parser.add_argument("--run-id")
    parser.add_argument("--project-id")
    parser.add_argument("--node-id")
    parser.add_argument("--parent-node-id")
    parser.add_argument("--model")
    parser.add_argument("--model-params")
    parser.add_argument("--seed")
    parser.add_argument("--created-at", help="ISO-8601 creation time; set it for byte-reproducible artifacts")
    parser.add_argument("--review-artifact", help="Independent review JSON bound to the canonical input hash")
    parser.add_argument("--validate-only", action="store_true", help="Validate a non-interactive Root input and emit only draft artifacts")
    parser.add_argument("--output", "-o", help="输出PRD文件路径")

    args = parser.parse_args(argv)

    if args.resume:
        try:
            return _resume_session(Path(args.resume), args) or EXIT_SUCCESS
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"Resume dependency error: {exc}")
            return EXIT_DEPENDENCY_ERROR

    if args.input:
        return run_root_noninteractive(args)

    # Interactive mode selection
    mode = _select_mode_interactive(args)

    try:
        if mode == Mode.DERIVE:
            if args.derive_all:
                if not args.parent_prd or not (args.architecture_package or args.parent_architecture) or not args.output_dir:
                    parser.error("--derive-all requires --parent-prd, --architecture-package, and --output-dir")
                return run_derive_all_mode(args)
            args = _prompt_derive_inputs(args)
            return run_derive_mode(args)
        return run_root_mode(args) or EXIT_SUCCESS
    except UnicodeDecodeError as exc:
        print(f"Dependency/input encoding error: {exc}")
        return EXIT_DEPENDENCY_ERROR
    except Exception as exc:  # CLI boundary: never turn a failure into success.
        print(f"Runtime error: {exc}")
        return EXIT_RUNTIME_ERROR


if __name__ == "__main__":
    sys.exit(main())
