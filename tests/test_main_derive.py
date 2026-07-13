from argparse import Namespace
from unittest.mock import patch

from prd_flow.main import EXIT_QUALITY_BLOCKED, EXIT_SUCCESS, run_derive_mode


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
        "related_requirements": [{"id": "REQ-001", "text": "系统展示按查询和画像匹配度排序的亚马逊商品", "priority": "Must Have"}],
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
    assert "```gherkin" not in text
    assert "Scenario:" not in text


@patch("prd_flow.main.save_session")
@patch("prd_flow.main.build_derive_context")
def test_derive_blocks_instead_of_inventing_missing_oracle(build, _save, tmp_path):
    build.return_value = context([])
    result = run_derive_mode(args(tmp_path))
    assert result == EXIT_QUALITY_BLOCKED
    draft = tmp_path / "derived.draft.md"
    assert draft.exists()
    text = draft.read_text(encoding="utf-8")
    assert "返回预期" not in text
    assert "```gherkin" not in text
