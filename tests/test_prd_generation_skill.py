from pathlib import Path


SKILL = Path("skills/prd-generation/SKILL.md")
REFERENCE = Path("skills/prd-generation/references/prd-to-gherkin-handoff-contract.md")


def read_skill():
    return SKILL.read_text(encoding="utf-8")


def test_skill_has_root_derive_and_handoff_contract():
    text = read_skill()
    assert "## Root Workflow" in text
    assert "## Derive Workflow" in text
    assert "prd-to-gherkin-handoff-contract.md" in text
    assert REFERENCE.exists()


def test_prd_generation_does_not_own_tc_or_gherkin():
    text = read_skill()
    assert "does **not** generate test cases or Gherkin" in text
    assert "downstream test skill owns Requirement Model, test design, TC" in text


def test_all_current_priorities_are_oracle_bound():
    text = read_skill()
    assert "every current `Must`, `Should`, and `Could` clause needs complete coverage" in text


def test_skill_requires_complete_functional_and_nfr_contracts():
    text = read_skill()
    reference = REFERENCE.read_text(encoding="utf-8")
    for field in ("actor", "preconditions", "trigger", "response", "observable_oracles", "boundaries", "exceptions"):
        assert field in reference
    for field in ("population", "measurement_start", "measurement_end", "unit", "threshold", "exclusions", "pass_rule"):
        assert field in reference
    assert "zero `blocked` rows" in text


def test_skill_forbids_oracle_invention_and_auto_scenarios():
    text = read_skill()
    assert "Never create a success response, error response, boundary, threshold, or exclusion" in text
    assert "Do not generate a placeholder scenario" in text


def test_derive_blocks_empty_or_oracle_incomplete_children_atomically():
    text = read_skill()
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "at least one inherited current-release obligation" in text
    assert "complete compatible parent Acceptance Contract" in text
    assert "leaves existing outputs unchanged" in text
    assert "unresolved metric reference" in reference


def test_derive_uses_generic_declarative_contract_projections():
    text = read_skill()
    reference = REFERENCE.read_text(encoding="utf-8")
    assert "acceptance-contract-projections.yaml" in text
    assert "Never special-case a product or module in code" in text
    assert "Existing child output is never used as projection evidence" in reference


def test_skill_requires_independent_agent_review():
    text = read_skill()
    assert "independent Agent review" in text
    assert "ready_for_test_generation: true" in text


def test_root_flow_closes_blockers_before_handoff():
    text = read_skill()
    assert "### R6A. Oracle Closure Loop" in text
    assert "Ask exactly one choice-first question at a time" in text
    assert "do not recommend or run downstream test generation" in text
    assert "Should" in text and "Could" in text and "explicit release-scope decision" in text


def test_skill_distinguishes_deterministic_and_statistical_quality_rules():
    text = read_skill()
    assert "deterministic_invariant" in text
    assert "statistical_nfr" in text


def test_skill_has_two_terminal_states_and_quality_report_resume():
    text = read_skill()
    assert "### Terminal States and Handoff Gate" in text
    assert "`*.draft.md`" in text
    assert "### R8. Resume from a Downstream Quality Report" in text
    assert "do not restart Root elicitation" in text
