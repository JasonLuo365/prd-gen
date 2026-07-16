from argparse import Namespace
from unittest.mock import patch

from pathlib import Path

from prd_flow.main import EXIT_QUALITY_BLOCKED, EXIT_SUCCESS, run_derive_all_mode, run_derive_mode


def args(tmp_path):
    return Namespace(parent_prd="parent.md", parent_architecture="arch.yaml", architecture_package=None, target_module="Recommendation Module", target_granularity="auto", output=str(tmp_path / "derived.md"), resume=None)


def contract():
    return {"id": "AC-ROOT-001", "type": "functional", "verifies": ["REQ-001"], "release_scope": "current", "actor": "user", "preconditions": ["purchase history and reviews exist"], "trigger": "asks for a recommendation", "response": ["Amazon products are ranked by query and profile fit"], "observable_oracles": ["ranked order is displayed"], "boundaries": ["new target domain -> use cross-domain stable profile"], "exceptions": ["Amazon API unavailable -> retrieval failure displayed"], "evidence_refs": ["parent:AC-ROOT-001"]}


def context(contracts):
    return {
        "success": True,
        "parent_doc_id": "ROOT-v1",
        "parent_arch_id": "ARCH-v1",
        "module_name": "Recommendation Module",
        "module": {"name": "Recommendation Module", "responsibility": "rank Amazon products"},
        "related_requirements": [{"id": "REQ-001", "text": "系统展示按查询和画像匹配度排序的亚马逊商品", "priority": "Must Have", "evidence_refs": ["DEC-001"]}],
        "related_architecture_requirements": [],
        "related_non_functional": [],
        "related_success_metrics": [],
        "related_acceptance_contracts": contracts,
        "related_scenarios": [],
        "interfaces": [], "events": [], "dependencies": [], "external_dependencies": [], "data_assets": [],
        "implementation_surfaces": ["domain_logic"], "requirement_surfaces": {"REQ-001": ["domain_logic"]},
        "interface_parent_refs": {}, "data_parent_refs": [], "artifact_parent_refs": {},
        "non_goals": [], "orphan_requirements": [], "derive_warnings": [], "coverage_gaps": [], "coverage_ledger": [{"id": "REQ-001", "status": "inherited_by_target"}],
    }


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_derive_succeeds_only_with_explicit_parent_contract(build, _save, tmp_path):
    build.return_value = context([contract()])
    result = run_derive_mode(args(tmp_path))
    assert result == EXIT_SUCCESS
    text = (tmp_path / "derived.md").read_text(encoding="utf-8")
    assert "D-AC-ROOT-001" in text
    assert "parent_acceptance_contract:AC-ROOT-001" in text
    assert "evidence_refs: [DEC-001, parent_requirement:REQ-001]" in text
    assert "```gherkin" not in text
    assert "Scenario:" not in text


@patch("prd_flow.main.build_derive_context")
def test_derive_blocks_when_parent_requirement_has_no_acceptance_contract(build, tmp_path):
    build.return_value = context([])
    result = run_derive_mode(args(tmp_path))
    assert result == EXIT_QUALITY_BLOCKED
    output = tmp_path / "derived.md"
    assert not output.exists()


@patch("prd_flow.main.build_derive_context")
def test_derive_blocks_when_target_has_no_current_requirement(build, tmp_path):
    derived_context = context([])
    derived_context["related_requirements"] = []
    derived_context["coverage_ledger"] = []
    build.return_value = derived_context

    assert run_derive_mode(args(tmp_path)) == EXIT_QUALITY_BLOCKED
    assert not (tmp_path / "derived.md").exists()


@patch("prd_flow.main.build_derive_context")
def test_derive_remaps_metric_requirement_refs_to_child_ids(build, tmp_path):
    derived_context = context([contract()])
    derived_context["related_success_metrics"] = [
        {
            "id": "MET-001",
            "name": "ranking success",
            "target": ">= 95%",
            "method": "count successful ranked responses",
            "requirement_refs": ["REQ-001"],
        }
    ]
    build.return_value = derived_context

    assert run_derive_mode(args(tmp_path)) == EXIT_SUCCESS
    text = (tmp_path / "derived.md").read_text(encoding="utf-8")
    assert "verifies: [REQ-D001]" in text


@patch("prd_flow.main.build_derive_context")
def test_derive_does_not_repeat_derived_contract_prefix(build, tmp_path):
    inherited = contract()
    inherited["id"] = "D-AC-ROOT-001"
    build.return_value = context([inherited])

    assert run_derive_mode(args(tmp_path)) == EXIT_SUCCESS
    text = (tmp_path / "derived.md").read_text(encoding="utf-8")
    assert "## D-AC-ROOT-001" in text
    assert "D-D-AC" not in text


@patch("prd_flow.main.build_derive_context")
def test_derive_blocks_partial_contract_without_declarative_projection(build, tmp_path):
    partial = contract()
    partial["verifies"] = ["REQ-001", "REQ-002"]
    build.return_value = context([partial])

    assert run_derive_mode(args(tmp_path)) == EXIT_QUALITY_BLOCKED
    assert not (tmp_path / "derived.md").exists()


@patch("prd_flow.main.build_derive_context")
def test_derive_applies_generic_child_contract_projection(build, tmp_path):
    partial = contract()
    partial["verifies"] = ["REQ-001", "REQ-002"]
    build.return_value = context([partial])
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "acceptance-contract-projections.yaml").write_text(
        """acceptance_contract_projections:
  - target_module: Recommendation Module
    parent_contract: AC-ROOT-001
    mode: project
    contract:
      actor: child actor
      preconditions: [child ready]
      trigger: child request
      response: [child response]
      observable_oracles: [child result visible]
      boundaries: [child limit -> child bounded response]
      exceptions: [child failure -> child error response]
      evidence_refs: [architecture:projection]
""",
        encoding="utf-8",
    )
    derive_args = args(tmp_path)
    derive_args.architecture_package = str(architecture)

    assert run_derive_mode(derive_args) == EXIT_SUCCESS
    text = (tmp_path / "derived.md").read_text(encoding="utf-8")
    assert "actor: child actor" in text
    assert "contract_projection:Recommendation Module:project" in text


@patch("prd_flow.main.build_derive_context")
def test_derive_does_not_convert_architecture_prose_into_requirements(build, tmp_path):
    derived_context = context([contract()])
    derived_context["related_architecture_requirements"] = [
        {"id": "ARCH-001", "text": "add a worker", "source_kind": "architecture_worker"}
    ]
    derived_context["artifact_parent_refs"] = {"worker": ["ARCH-001"]}
    derived_context["implementation_surfaces"] = ["worker_job"]
    build.return_value = derived_context

    assert run_derive_mode(args(tmp_path)) == EXIT_SUCCESS
    text = (tmp_path / "derived.md").read_text(encoding="utf-8")
    assert "REQ-A" not in text
    assert "add a worker" not in text


@patch("prd_flow.main.build_derive_context")
def test_single_derive_uses_layered_output_dir(build, tmp_path):
    derived_context = context([contract()])
    derived_context["module_name"] = "cfg-package-validation"
    derived_context["module"] = {"name": "cfg-package-validation", "responsibility": "validate configuration packages"}
    build.return_value = derived_context
    product_root = tmp_path / "product"
    parent_prd = product_root / "L1" / "L1-configuration-governance" / "prd.md"
    parent_prd.parent.mkdir(parents=True)
    parent_prd.write_text("---\nmodule_name: Configuration Governance\n---\n", encoding="utf-8")
    derive_args = args(tmp_path)
    derive_args.parent_prd = str(parent_prd)
    derive_args.target_module = "cfg-package-validation"
    derive_args.output = None
    derive_args.output_dir = str(product_root)

    assert run_derive_mode(derive_args) == EXIT_SUCCESS
    assert (product_root / "L2" / "cg" / "L2-cg-package-validation" / "prd.md").exists()


def derive_all_args(tmp_path, allocation_report=None, parent_prd="parent.md"):
    return Namespace(
        parent_prd=str(parent_prd),
        parent_architecture="architecture",
        architecture_package=None,
        target_module=None,
        target_granularity="auto",
        output=None,
        output_dir=str(tmp_path),
        allocation_report=allocation_report,
        derive_all=True,
        resume=None,
    )


@patch("prd_flow.main.run_derive_mode")
@patch("prd_flow.main.build_layer_allocation")
def test_derive_all_writes_only_child_prds_by_default(build_allocation, derive, tmp_path):
    build_allocation.return_value = {
        "success": True,
        "parent_doc_id": "ROOT-v1",
        "target_modules": ["Module A", "Module B"],
        "ledger": [],
        "errors": [],
        "contexts": {},
    }

    def write_child(child_args):
        Path(child_args.output).write_text("# Child PRD\n", encoding="utf-8")
        return EXIT_SUCCESS

    derive.side_effect = write_child

    product_root = tmp_path / "product"
    parent_prd = product_root / "L0" / "L0-root" / "prd.md"
    assert run_derive_all_mode(derive_all_args(product_root, parent_prd=parent_prd)) == EXIT_SUCCESS
    assert sorted(path.relative_to(product_root).as_posix() for path in product_root.rglob("*")) == [
        "L1",
        "L1/L1-module-a",
        "L1/L1-module-a/prd.md",
        "L1/L1-module-b",
        "L1/L1-module-b/prd.md",
    ]


@patch("prd_flow.main.run_derive_mode")
@patch("prd_flow.main.build_layer_allocation")
def test_derive_all_groups_next_layer_by_parent_abbreviation(build_allocation, derive, tmp_path):
    build_allocation.return_value = {
        "success": True,
        "parent_doc_id": "CONFIGURATION-GOVERNANCE-v1",
        "target_modules": ["cfg-package-validation", "cfg-version-registry"],
        "ledger": [],
        "errors": [],
        "contexts": {},
    }

    def write_child(child_args):
        Path(child_args.output).write_text("# Child PRD\n", encoding="utf-8")
        return EXIT_SUCCESS

    derive.side_effect = write_child
    product_root = tmp_path / "product"
    parent_prd = product_root / "L1" / "L1-configuration-governance" / "prd.md"
    parent_prd.parent.mkdir(parents=True)
    parent_prd.write_text("---\nmodule_name: Configuration Governance\n---\n", encoding="utf-8")

    assert run_derive_all_mode(derive_all_args(product_root, parent_prd=parent_prd)) == EXIT_SUCCESS
    assert (product_root / "L2" / "cg" / "L2-cg-package-validation" / "prd.md").exists()
    assert (product_root / "L2" / "cg" / "L2-cg-version-registry" / "prd.md").exists()


@patch("prd_flow.main.run_derive_mode")
@patch("prd_flow.main.build_layer_allocation")
def test_derive_all_failure_leaves_existing_outputs_unchanged(build_allocation, derive, tmp_path):
    build_allocation.return_value = {
        "success": True,
        "parent_doc_id": "ROOT-v1",
        "target_modules": ["Module A", "Module B"],
        "ledger": [],
        "errors": [],
        "contexts": {},
    }
    existing = tmp_path / "L1-module-a" / "prd.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")

    def generate(child_args):
        if child_args.target_module == "Module B":
            return EXIT_QUALITY_BLOCKED
        Path(child_args.output).write_text("replacement\n", encoding="utf-8")
        return EXIT_SUCCESS

    derive.side_effect = generate

    assert run_derive_all_mode(derive_all_args(tmp_path)) == EXIT_QUALITY_BLOCKED
    assert existing.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / "L1-module-b").exists()


@patch("prd_flow.main.run_derive_mode", return_value=EXIT_SUCCESS)
@patch("prd_flow.main.build_layer_allocation")
def test_derive_all_writes_allocation_report_only_when_requested(build_allocation, _derive, tmp_path):
    build_allocation.return_value = {
        "success": True,
        "parent_doc_id": "ROOT-v1",
        "target_modules": [],
        "ledger": [{"id": "REQ-001", "status": "allocated"}],
        "errors": [],
        "contexts": {"not": "serialized"},
    }
    report = tmp_path / "diagnostics" / "allocation.json"

    assert run_derive_all_mode(derive_all_args(tmp_path / "out", str(report))) == EXIT_SUCCESS
    assert report.exists()
    assert "contexts" not in report.read_text(encoding="utf-8")
