from pathlib import Path


def test_fillable_template_exists():
    template_path = Path("prd_flow/templates/prd_fillable_template.md")
    assert template_path.exists()
    content = template_path.read_text(encoding="utf-8")
    assert "---" in content  # YAML frontmatter
    assert "Requirements" in content
    assert "Acceptance" in content
    assert "Success Metrics" in content
    assert "Must Have" in content
    assert "```gherkin" in content
    assert "[请填写" in content  # 模板中有明确的待填写标记
