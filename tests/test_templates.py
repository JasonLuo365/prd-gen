from pathlib import Path


def test_fillable_template_is_oracle_ready_and_has_no_gherkin():
    content = Path("prd_flow/templates/prd_fillable_template.md").read_text(encoding="utf-8")
    assert "Atomic Requirements" in content
    assert "Functional Acceptance Contract" in content
    assert "NFR Verification Contract" in content
    assert "Oracle Coverage Ledger" in content
    assert "```gherkin" not in content
    assert "Scenario:" not in content


def test_runtime_template_has_readiness_sections():
    content = Path("prd_flow/templates/prd_template.md").read_text(encoding="utf-8")
    assert "ready_for_test_generation" in content
    assert "oracle_blocked_count" in content
    assert "Agent Review Report" in content
