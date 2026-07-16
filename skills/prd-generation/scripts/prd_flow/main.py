"""Main CLI entry point for PRD Flow."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
import uuid
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
from prd_flow.quality.oracle import check_oracle_coverage
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
    """Load declarative child-contract projections; never infer missing oracle fields."""
    architecture_path = Path(architecture_input)
    if not architecture_path.is_dir():
        return {}
    projection_path = architecture_path / "acceptance-contract-projections.yaml"
    if not projection_path.exists():
        return {}
    payload = yaml.safe_load(projection_path.read_text(encoding="utf-8")) or {}
    records = payload.get("acceptance_contract_projections", [])
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


def _run_ambiguity_check(state: SessionState, prd_text: str) -> dict:
    """对PRD文本运行歧义扫描。"""
    functional = state.draft_content.get("P3", {}).get("functional", [])
    return scan_ambiguity(prd_text, functional)


def _ask_continue(prompt: str) -> bool:
    """询问用户是否继续。"""
    answer = input(f"{prompt} (y/n): ").strip().lower()
    return answer in ("y", "yes", "是")


def _write_error_report(state: SessionState, errors: list, args: argparse.Namespace) -> None:
    """Write draft PRD and JSON error report on quality failure."""
    if state.mode == "derive":
        print("\n[ERROR] Derive failed:")
        for error in errors:
            print(f"  - {error}")
        return

    # Assemble partial PRD and write to .draft.md
    prd_text = assemble_prd(state.draft_content)
    parent_doc = state.draft_content.get("P1", {}).get("parent_doc", "unknown")
    module_name = state.draft_content.get("P1", {}).get("module_name", "unknown")
    version = state.draft_content.get("P1", {}).get("version", "1.0.0")
    draft_path = Path(args.output) if args.output else Path(f"{parent_doc}_{module_name}_prd_v{version}.md")
    if not draft_path.name.endswith(".draft.md"):
        draft_path = draft_path.with_suffix(".draft.md")
    draft_path.write_text(prd_text, encoding="utf-8")

    # Write JSON error report to .draft.errors.json
    errors_path = draft_path.with_suffix(".errors.json")
    errors_path.write_text(
        json.dumps({"errors": errors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

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

    # Save PRD to file
    project_name = state.draft_content["P1"].get("project_name", "unknown")
    version = state.draft_content["P1"].get("version", "1.0.0")
    output_path = Path(args.output) if args.output else Path(f"{project_name}_prd_v{version}.md")
    output_path.write_text(prd_text, encoding="utf-8")
    print(f"\nPRD已保存至: {output_path}")

    # Save session
    session_path = Path(f".prd_session_{state.session_id}.json")
    save_session(state, session_path)
    print(f"会话已保存至: {session_path}")


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
    context = build_derive_context(
        Path(args.parent_prd),
        Path(architecture_input),
        target_module,
        target_granularity=target_granularity,
    )

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
    for index, req in enumerate(authoritative_requirements, start=1):
        req_id = req.get("id", "REQ-UNKNOWN")
        req_text = _clean_req_text(req.get("text", ""))
        parent_priority = req.get("priority", "Must Have")
        child_id = f"REQ-D{index:03d}"
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

    architecture_req_index = 1
    interface_req_ids: dict[str, str] = {}
    parent_arch_to_child: dict[str, str] = {}
    # Architecture determines child ownership only. Derive must not turn
    # architecture descriptions into new product requirements.
    artifact_parent_refs: dict[str, list[str]] = {}

    frontend_requirement_id: str | None = None
    frontend_related_reqs = [
        parent_to_child[req.get("id", "")]
        for req in authoritative_requirements
        if "frontend" in context.get("requirement_surfaces", {}).get(req.get("id", ""), [])
        and req.get("id", "") in parent_to_child
    ]
    if (
        "frontend" in implementation_surfaces
        and frontend_related_reqs
        and artifact_parent_refs.get("frontend")
    ):
        frontend_requirement_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_frontend_refs = list(dict.fromkeys(artifact_parent_refs.get("frontend", [])))
        for parent_ref in parent_frontend_refs:
            parent_arch_to_child[parent_ref] = frontend_requirement_id
        frontend_contracts = [
            " ".join(
                part
                for part in (interface.get("method", ""), interface.get("path", ""))
                if part
            )
            for interface in actionable_interfaces
            if "web app" in str(interface.get("consumer", "")).casefold()
        ]
        contract_clause = (
            f"并通过父架构声明的 {', '.join(frontend_contracts)} 完成交互"
            if frontend_contracts
            else "并通过父架构声明的公开接口完成交互"
        )
        functional.append(
            {
                "id": frontend_requirement_id,
                "text": (
                    f"{module_name} 必须提供可部署、可测试的学生端前端实现，包含完成 "
                    f"{', '.join(frontend_related_reqs)} 及其父级验收场景所需的页面、组件、交互状态和 API 客户端，"
                    f"{contract_clause}；输入、点击、选择、上传、禁用、展示、错误提示和重试等可观察行为"
                    "不得以 API 实现或后端测试替代。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_frontend_refs)
                    if parent_frontend_refs
                    else "ARCH:03-runtime-architecture.md#Web App"
                ),
                "related_reqs": frontend_related_reqs,
                "source_kind": "architecture_frontend",
                "implementation_surfaces": ["frontend"],
            }
        )

    for interface in actionable_interfaces:
        interface_id = interface.get("contract_id") or interface.get("name") or interface.get("path")
        child_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        interface_req_ids[str(interface_id)] = child_id
        parent_interface_refs = context.get("interface_parent_refs", {}).get(str(interface_id), [])
        if not parent_interface_refs:
            continue
        for parent_ref in parent_interface_refs:
            parent_arch_to_child[parent_ref] = child_id
        operation = " ".join(
            part for part in (interface.get("method", ""), interface.get("path", "")) if part
        )
        request_fields = ", ".join(interface.get("request_fields", []))
        response_fields = ", ".join(interface.get("response_fields", []))
        error_codes = ", ".join(interface.get("error_codes", []))
        error_clause = f"；错误码仅使用架构已声明的 {error_codes}" if error_codes else ""
        interface_role = interface.get("ownership_role", "provider")
        role_clause = {
            "consumer": "必须集成、消费并处理父架构接口",
            "provider_and_consumer": "必须提供、集成并消费父架构接口",
        }.get(interface_role, "必须提供并实现父架构接口")
        functional.append(
            {
                "id": child_id,
                "text": (
                    f"{module_name} {role_clause} {interface.get('name', interface_id)}（{operation}）："
                    f"输入字段为 {request_fields}；输出字段为 {response_fields}{error_clause}。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_interface_refs)
                    if parent_interface_refs
                    else f"ARCH:06-interface-contracts.md#{interface_id}"
                ),
                "source_kind": "architecture_interface",
                "implementation_surfaces": ["api_backend"],
            }
        )

    data_requirement_id: str | None = None
    if data_assets and context.get("data_parent_refs", []):
        data_requirement_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_data_refs = context.get("data_parent_refs", [])
        for parent_ref in parent_data_refs:
            parent_arch_to_child[parent_ref] = data_requirement_id
        asset_names = ", ".join(asset.get("name", "UNKNOWN") for asset in data_assets)
        functional.append(
            {
                "id": data_requirement_id,
                "text": (
                    f"{module_name} 必须为父架构定义的数据聚合 {asset_names} 及其在 05-data-model.md 中声明的"
                    "实体和必需字段提供版本化持久化结构与数据库迁移，并验证迁移可在受支持的空数据库上完整创建所需结构。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_data_refs)
                    if parent_data_refs
                    else "ARCH:05-data-model.md"
                ),
                "source_kind": "architecture_data",
                "implementation_surfaces": ["database_migration"],
            }
        )

    event_req_ids: dict[str, str] = {}
    for event in events:
        event_key = str(event.get("contract_id") or event.get("event_name"))
        child_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        event_req_ids[event_key] = child_id
        parent_event_refs = artifact_parent_refs.get(f"event:{event_key}", [])
        if not parent_event_refs:
            continue
        for parent_ref in parent_event_refs:
            parent_arch_to_child[parent_ref] = child_id
        required_fields = ", ".join(event.get("required_fields", []))
        produced_fields = ", ".join(event.get("produced_fields", []))
        functional.append(
            {
                "id": child_id,
                "text": (
                    f"{module_name} 必须按父架构事件契约生成、发布或处理事件 {event.get('event_name', event_key)}："
                    f"发布者为 {event.get('publisher', 'UNKNOWN')}；消费者为 {event.get('consumers', 'UNKNOWN')}；"
                    f"必需字段为 {required_fields}；产出字段为 {produced_fields}；"
                    f"副作用为 {event.get('side_effects', 'None')}。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_event_refs)
                    if parent_event_refs
                    else f"ARCH:06-interface-contracts.md#{event_key}"
                ),
                "source_kind": "architecture_event",
                "implementation_surfaces": ["domain_logic"],
            }
        )

    adapter_req_ids: dict[str, str] = {}
    for dependency in external_dependencies:
        dependency_name = str(dependency.get("name", "UNKNOWN"))
        normalized_dependency = "".join(ch.lower() for ch in dependency_name if ch.isalnum())
        artifact_key = f"adapter:{normalized_dependency}"
        child_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        adapter_req_ids[normalized_dependency] = child_id
        parent_adapter_refs = artifact_parent_refs.get(artifact_key, [])
        if not parent_adapter_refs:
            continue
        for parent_ref in parent_adapter_refs:
            parent_arch_to_child[parent_ref] = child_id
        evidence = _clean_req_text(str(dependency.get("evidence", "父架构依赖声明")))
        functional.append(
            {
                "id": child_id,
                "text": (
                    f"{module_name} 必须提供外部依赖适配器 {dependency_name}，并按父架构证据“{evidence}”"
                    "封装调用、失败处理和领域边界，禁止把适配器实现视为外部团队自动提供。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_adapter_refs)
                    if parent_adapter_refs
                    else f"ARCH:{dependency.get('source', 'architecture')}#{dependency_name}"
                ),
                "source_kind": "architecture_adapter",
                "implementation_surfaces": ["external_adapter"],
            }
        )

    worker_requirement_id: str | None = None
    if "worker_job" in implementation_surfaces and artifact_parent_refs.get("worker"):
        worker_requirement_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_worker_refs = artifact_parent_refs.get("worker", [])
        for parent_ref in parent_worker_refs:
            parent_arch_to_child[parent_ref] = worker_requirement_id
        functional.append(
            {
                "id": worker_requirement_id,
                "text": (
                    f"{module_name} 必须提供父架构定义的 Worker/调度作业入口，执行该模块拥有的定时或异步行为，"
                    "并记录可验证的成功、失败与重试结果。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_worker_refs)
                    if parent_worker_refs
                    else "ARCH:03-runtime-architecture.md#worker"
                ),
                "source_kind": "architecture_worker",
                "implementation_surfaces": ["worker_job"],
            }
        )

    runtime_requirement_id: str | None = None
    if (
        "integration_wiring" in implementation_surfaces
        and artifact_parent_refs.get(f"runtime:{module_name}")
    ):
        runtime_requirement_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_runtime_refs = artifact_parent_refs.get(f"runtime:{module_name}", [])
        for parent_ref in parent_runtime_refs:
            parent_arch_to_child[parent_ref] = runtime_requirement_id
        functional.append(
            {
                "id": runtime_requirement_id,
                "text": (
                    f"{module_name} 必须提供可由父层运行时装配的公开入口、配置和集成连接点，"
                    "并验证模块在父架构部署拓扑中可启动且已声明契约可达；父层 wiring 不得被当作无需实现。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_runtime_refs)
                    if parent_runtime_refs
                    else "ARCH:03-runtime-architecture.md;ARCH:08-deployment.md"
                ),
                "source_kind": "architecture_runtime",
                "implementation_surfaces": ["integration_wiring"],
            }
        )

    observability_requirement_id: str | None = None
    related_success_metrics = context.get("related_success_metrics", [])
    related_non_functional = context.get("related_non_functional", [])
    observable_nfrs = [
        nfr
        for nfr in related_non_functional
        if any(
            marker in nfr.get("text", "").casefold()
            for marker in ("p95", "p99", "%", "成功率", "可追溯", "审计", "测量", "日志", "指标")
        )
    ]
    if (
        (related_success_metrics or observable_nfrs)
        and artifact_parent_refs.get(f"observability:{module_name}")
    ):
        observability_requirement_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_observability_refs = artifact_parent_refs.get(
            f"observability:{module_name}",
            [],
        )
        for parent_ref in parent_observability_refs:
            parent_arch_to_child[parent_ref] = observability_requirement_id
        metric_parts = [
            f"{metric.get('name', metric.get('id', 'metric'))} {metric.get('target', '')}".strip()
            for metric in related_success_metrics
        ]
        metric_parts.extend(
            f"{nfr.get('id', 'NFR')} {nfr.get('text', '')}" for nfr in observable_nfrs
        )
        metric_summary = "; ".join(metric_parts)
        metric_refs = [
            metric.get("id") or metric.get("name", "metric")
            for metric in related_success_metrics
        ]
        metric_refs.extend(nfr.get("id", "NFR") for nfr in observable_nfrs)
        functional.append(
            {
                "id": observability_requirement_id,
                "text": (
                    f"{module_name} 必须记录并提供可验证的观测证据以测量父级成功指标：{metric_summary}；"
                    "证据的统计口径、起止点和排除条件必须沿用父级定义。"
                ),
                "priority": "Must Have",
                "parent_req": (
                    ", ".join(parent_observability_refs)
                    if parent_observability_refs
                    else "MET:" + ", ".join(metric_refs)
                ),
                "source_kind": "architecture_observability",
                "implementation_surfaces": ["observability"],
            }
        )

    inherited_architecture_req_ids: dict[str, str] = {}
    related_architecture_requirements: list[dict] = []
    for parent_arch_req in related_architecture_requirements:
        parent_id = parent_arch_req.get("id", "")
        if not parent_id or parent_id in parent_arch_to_child:
            continue
        child_id = f"REQ-A{architecture_req_index:03d}"
        architecture_req_index += 1
        parent_arch_to_child[parent_id] = child_id
        inherited_architecture_req_ids[parent_id] = child_id
        source_kind = parent_arch_req.get("source_kind", "architecture_inherited")
        default_surfaces = {
            "architecture_frontend": ["frontend"],
            "architecture_event": ["domain_logic"],
            "architecture_adapter": ["external_adapter"],
            "architecture_worker": ["worker_job"],
        }.get(source_kind, ["domain_logic"])
        functional.append(
            {
                "id": child_id,
                "text": (
                    f"{module_name} 应在自身架构边界内继续满足父级架构义务："
                    f"{_clean_req_text(parent_arch_req.get('text', ''))}"
                ),
                "priority": parent_arch_req.get("priority", "Must Have"),
                "parent_req": parent_id,
                "source_kind": source_kind,
                "implementation_surfaces": parent_arch_req.get(
                    "implementation_surfaces",
                    default_surfaces,
                ),
            }
        )

    non_functional = []
    parent_nfr_to_child: dict[str, str] = {}
    for index, nfr in enumerate(related_non_functional, start=1):
        child_nfr_id = f"NFR-D{index:03d}"
        parent_nfr_to_child[nfr.get("id", "NFR-UNKNOWN")] = child_nfr_id
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
    parent_reference_mapping = {**parent_to_child, **parent_nfr_to_child, **parent_arch_to_child}
    parent_requirement_records = [*authoritative_requirements, *related_non_functional]
    for parent_contract in related_acceptance_contracts:
        verifies = parent_contract.get("verifies", [])
        if isinstance(verifies, str):
            verifies = [verifies]
        mapped = _map_parent_references(
            verifies,
            parent_requirement_records,
            parent_reference_mapping,
        )
        if not mapped:
            continue
        mapped_parent_refs = [
            reference
            for reference in verifies
            if _map_parent_references(
                [reference], parent_requirement_records, parent_reference_mapping
            )
        ]
        projection = contract_projections.get(
            (module_name, parent_contract.get("id", ""))
        )
        if len(mapped_parent_refs) < len(verifies) and not projection:
            contract_projection_errors.append(
                f"Partial parent contract {parent_contract.get('id', 'UNKNOWN')} for {module_name} "
                "requires acceptance-contract-projections.yaml."
            )
            continue
        contract = dict(parent_contract)
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
    parser.add_argument("--output", "-o", help="输出PRD文件路径")

    args = parser.parse_args(argv)

    if args.resume:
        _resume_session(Path(args.resume), args)
        return EXIT_SUCCESS

    # Interactive mode selection
    mode = _select_mode_interactive(args)

    if mode == Mode.DERIVE:
        if args.derive_all:
            if not args.parent_prd or not (args.architecture_package or args.parent_architecture) or not args.output_dir:
                parser.error("--derive-all requires --parent-prd, --architecture-package, and --output-dir")
            return run_derive_all_mode(args)
        args = _prompt_derive_inputs(args)
        return run_derive_mode(args)
    else:
        run_root_mode(args)
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
