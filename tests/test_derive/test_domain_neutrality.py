from pathlib import Path

from prd_flow.derive.context_builder import build_derive_context


def test_explicit_allocation_is_domain_neutral_and_architecture_adds_no_requirement(tmp_path: Path):
    parent = tmp_path / "parent.md"
    parent.write_text(
        """---
doc_id: PARENT-1
status: approved
ready_for_test_generation: true
---
# Requirements
### Must Have
- [REQ-001] The system records a reservation request.
  - source_kind: explicit
  - evidence_refs: [decision:1]
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-module-partitioning.md").write_text(
        """| Module | Responsibility | Source Requirement |
|---|---|---|
| Reservation Processor | durable processing | REQ-001 |
""",
        encoding="utf-8",
    )
    first = build_derive_context(parent, architecture, "Reservation Processor")
    (architecture / "04-contracts-and-runtime.md").write_text("A new transport protocol exists.", encoding="utf-8")
    second = build_derive_context(parent, architecture, "Reservation Processor")
    assert [item["id"] for item in first["related_requirements"]] == ["REQ-001"]
    assert [item["id"] for item in second["related_requirements"]] == ["REQ-001"]


def test_runtime_contains_no_product_specific_ownership_dictionary():
    root = Path("skills/prd-generation/scripts/prd_flow")
    text = (root / "derive" / "context_builder.py").read_text(encoding="utf-8")
    for forbidden in ("_owns_", "student app", "Math Recognition", "Image Submission"):
        assert forbidden not in text


def test_draft_parent_is_rejected_before_architecture_is_read(tmp_path: Path):
    parent = tmp_path / "parent.md"
    parent.write_text("---\nstatus: draft\nready_for_test_generation: false\n---\n", encoding="utf-8")
    result = build_derive_context(parent, tmp_path, "Any Module")
    assert result["success"] is False
    assert result["error"].startswith("PARENT_PRD_NOT_HANDOFF_READY")
