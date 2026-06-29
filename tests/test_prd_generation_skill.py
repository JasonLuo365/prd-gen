"""Static checks for the project-local PRD generation skill draft.

This file is intentionally executable with plain Python so the skill can be
validated even before pytest is installed in the workspace.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "prd-generation" / "SKILL.md"


def read_skill() -> str:
    assert SKILL_PATH.exists(), f"Missing skill file: {SKILL_PATH}"
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_frontmatter() -> None:
    text = read_skill()
    assert text.startswith("---\n")
    assert "\nname: prd-generation\n" in text
    assert "\ndescription: Use when" in text
    assert text.count("---") >= 2


def test_skill_contains_required_sections() -> None:
    text = read_skill()
    required = [
        "# PRD Generation",
        "## Trigger Mechanism",
        "## Mode Detection",
        "## Root Mode",
        "## Derive Mode",
        "## Quality Gates",
        "## Output Contract",
        "## Commands",
        "## Red Flags",
    ]
    for marker in required:
        assert marker in text, f"Missing section: {marker}"


def test_skill_encodes_root_and_derive_contracts() -> None:
    text = read_skill()
    assert "one question at a time" in text
    assert "Phase Completion Protocol" in text
    assert "quality gate plus user confirmation" in text
    assert "handoff checkpoint" in text
    assert "Do not auto-advance" in text
    assert "Requirements phase exit checklist" in text
    assert "block the transition" in text
    assert "choice-style options" in text
    assert "choice-first elicitation" in text
    assert "Other / supplement" in text
    assert "directions, not facts" in text
    assert "Recommended option" in text
    assert "pros and cons" in text
    assert "free-form answer" in text
    assert "answer template" in text
    assert "Do not invent a concrete project" in text
    assert "parent_prd" in text
    assert "architecture_package" in text
    assert "parent_architecture" in text
    assert "target_module" in text
    assert "target_granularity" in text
    assert "README.md" in text
    assert "zip" in text
    assert "python -m prd_flow" in text
    assert "If `prd_flow` is unavailable" in text
    assert "LLM fallback" in text
    assert "no interactive questions" in text


def test_skill_has_installable_metadata() -> None:
    metadata_path = SKILL_PATH.parent / "agents" / "openai.yaml"
    assert metadata_path.exists(), f"Missing skill UI metadata: {metadata_path}"
    metadata = metadata_path.read_text(encoding="utf-8")
    assert "display_name:" in metadata
    assert "short_description:" in metadata
    assert "default_prompt:" in metadata


def test_skill_defines_explicit_trigger_mechanism() -> None:
    text = read_skill()
    assert "explicit trigger phrase" in text
    assert "Root trigger phrases" in text
    assert "Derive trigger phrases" in text
    assert "Non-trigger phrases" in text
    assert "do not trigger" in text
    assert "生成顶层 PRD" in text
    assert "进入 Root 模式" in text
    assert "生成下层 PRD" in text
    assert "讨论这个 skill" in text
    assert "测试这个 skill" in text


def test_skill_guards_against_known_antipatterns() -> None:
    text = read_skill()
    assert "Do not ask field-by-field form questions" in text
    assert "Do not generate architecture or code" in text
    assert "Must-Have" in text
    assert "SMART-REQ" in text
    assert "scope" in text
    assert "priority" in text
    assert "TODO" not in text
    assert 'Do not use `defer`, `TBD`, or "future consideration"' in text


def test_root_mode_prefers_choice_first_questions() -> None:
    text = read_skill()
    assert "Root mode will primarily use choice questions" in text
    assert "Ask one choice-first decision at a time" in text
    assert "select, combine, remove, or supplement" in text
    assert "Do not present candidate capabilities as facts" in text
    assert "Only use a fully open question when there is too little context" in text


def test_skill_blocks_undefined_testcase_terms() -> None:
    text = read_skill()
    assert "Testcase Readiness Gate" in text
    assert "test-blocking qualifier" in text
    assert "operational definition" in text
    assert "baseline test set" in text
    assert "measurement start" in text
    assert "measurement end" in text
    assert "Blocking Questions" in text
    assert "Open Questions must not contain unresolved issues that block testcase generation" in text
    for qualifier in [
        "simple",
        "complex",
        "common",
        "critical",
        "normal",
        "high load",
        "timely",
        "stable",
        "accurate",
    ]:
        assert qualifier in text


def test_skill_requires_evidence_locked_testcase_generation() -> None:
    text = read_skill()
    assert "Evidence-Locked Testcase Gate" in text
    assert "Final Testcase Readiness Review" in text
    assert "Test Evidence and Decision Register" in text
    assert "Change Management Backlog" in text
    assert "non_blocking_test_impacting" in text
    assert "trigger" in text
    assert "boundary" in text
    assert "oracle" in text
    assert "natural hour vs rolling hour" in text
    assert "51st-upload behavior" in text
    assert "@auto-resolved-assumption" in text
    assert "Do not use `@auto-resolved-assumption`" in text
    assert "Do not treat non-blocking assumptions as irrelevant to testcase generation" in text
    assert "Do not generate or expand testcase scenarios for Change Management items" in text
    assert "What happens at `N`, `N+1`, and API bypass?" in text
    assert "rewrite the affected PRD sections" in text
    assert "Re-run the relevant quality gates and this final review" in text
    assert "Do not emit the final PRD while Final Testcase Readiness Review" in text


if __name__ == "__main__":
    test_skill_frontmatter()
    test_skill_contains_required_sections()
    test_skill_encodes_root_and_derive_contracts()
    test_skill_has_installable_metadata()
    test_skill_defines_explicit_trigger_mechanism()
    test_skill_guards_against_known_antipatterns()
    test_root_mode_prefers_choice_first_questions()
    test_skill_blocks_undefined_testcase_terms()
    test_skill_requires_evidence_locked_testcase_generation()
    print("PRD generation skill static checks passed.")
