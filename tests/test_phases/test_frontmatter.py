from unittest.mock import patch

from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.session import SessionState


def test_frontmatter_phase_generates_metadata():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )
    phase = FrontmatterPhase(state)

    # Simulate user providing project info
    result = phase.collect(
        project_name="ecommerce_platform",
        author="team",
        priority="P0",
    )

    assert result["doc_id"] == "ECOMMERCE-PLATFORM-v1.0"
    assert result["layer"] == "root"
    assert result["parent_doc"] is None
    assert result["version"] == "1.0.0"
    assert "project_name" in result
    assert result["project_name"] == "ecommerce_platform"


def test_frontmatter_phase_run_interactive():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )
    phase = FrontmatterPhase(state)

    with patch("builtins.input", side_effect=["my project", "Alice", "P1"]):
        result = phase.run()

    assert result["doc_id"] == "MY-PROJECT-v1.0"
    assert result["author"] == "Alice"
    assert result["priority"] == "P1"
    assert "P1" in state.completed_phases


def test_frontmatter_collect_derive_generates_correct_doc_id():
    parent_context = {
        "parent_doc_id": "ECOMMERCE-PLATFORM-v1.0",
        "parent_arch_id": "ECOMMERCE-PLATFORM-v1.0-ARCH",
        "module_name": "payment_gateway",
        "interfaces": [{"name": "create_payment", "method": "POST"}],
        "dependencies": [{"module": "user_auth", "type": "internal"}],
    }
    state = SessionState(
        session_id="sess_002",
        mode="derive",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
        parent_context=parent_context,
        target_module="payment_gateway",
    )
    phase = FrontmatterPhase(state)

    result = phase.collect_derive(
        parent_doc_id="ECOMMERCE-PLATFORM-v1.0",
        parent_arch_id="ECOMMERCE-PLATFORM-v1.0-ARCH",
        module_name="payment_gateway",
        interfaces=[{"name": "create_payment", "method": "POST"}],
        dependencies=[{"module": "user_auth", "type": "internal"}],
        priority="P1",
        author="Bob",
    )

    assert result["doc_id"] == "ECOMMERCE-PLATFORM-v1.0-PAYMENT-GATEWAY-v1.0"
    assert result["layer"] == "derive"
    assert result["parent_doc"] == "ECOMMERCE-PLATFORM-v1.0"
    assert result["parent_arch"] == "ECOMMERCE-PLATFORM-v1.0-ARCH"
    assert result["module_name"] == "payment_gateway"
    assert result["interface_refs"] == ["create_payment"]
    assert result["dependency_refs"] == ["user_auth"]
    assert result["event_refs"] == []
    assert "interfaces" not in result
    assert "dependencies" not in result
    assert "events" not in result
    assert result["priority"] == "P1"
    assert result["author"] == "Bob"
    assert result["version"] == "1.0.0"
    assert result["status"] == "complete"
    assert result["inheritance_complete"] is True
    assert "P1" in state.completed_phases


def test_frontmatter_derive_mode_run_interactive():
    parent_context = {
        "parent_doc_id": "ECOMMERCE-PLATFORM-v1.0",
        "parent_arch_id": "ECOMMERCE-PLATFORM-v1.0-ARCH",
        "module_name": "payment_gateway",
        "interfaces": [{"name": "create_payment", "method": "POST"}],
        "dependencies": [{"module": "user_auth", "type": "internal"}],
    }
    state = SessionState(
        session_id="sess_002",
        mode="derive",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
        parent_context=parent_context,
        target_module="payment_gateway",
    )
    phase = FrontmatterPhase(state)

    # In derive mode, run() no longer asks for priority (uses default P0)
    result = phase.run()

    assert result["doc_id"] == "ECOMMERCE-PLATFORM-v1.0-PAYMENT-GATEWAY-v1.0"
    assert result["layer"] == "derive"
    assert result["parent_doc"] == "ECOMMERCE-PLATFORM-v1.0"
    assert result["parent_arch"] == "ECOMMERCE-PLATFORM-v1.0-ARCH"
    assert result["module_name"] == "payment_gateway"
    assert result["priority"] == "P0"
    assert "P1" in state.completed_phases


def test_frontmatter_collect_derive_defaults_parent_arch():
    """If parent_arch_id is not provided, derive it from parent_doc_id."""
    state = SessionState(
        session_id="sess_003",
        mode="derive",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
        parent_context={},
        target_module="payment_gateway",
    )
    phase = FrontmatterPhase(state)

    result = phase.collect_derive(
        parent_doc_id="ECOMMERCE-PLATFORM-v1.0",
        parent_arch_id=None,  # type: ignore[arg-type]
        module_name="payment_gateway",
        interfaces=[],
        dependencies=[],
    )

    assert result["parent_arch"] == "ECOMMERCE-PLATFORM-v1.0-ARCH"


def test_frontmatter_collect_derive_emits_stable_compact_refs():
    state = SessionState(
        session_id="sess_004",
        mode="derive",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
        parent_context={},
        target_module="recommendation",
    )
    phase = FrontmatterPhase(state)

    result = phase.collect_derive(
        parent_doc_id="ASSISTANT-v1.0",
        parent_arch_id="ASSISTANT-v1.0-ARCH",
        module_name="recommendation",
        interfaces=[
            {"contract_id": "IF-001", "name": "rank", "request": {"large": "record"}},
            {"contract_id": "IF-001", "name": "rank_duplicate"},
            {"name": "explain"},
        ],
        dependencies=[
            {"name": "profile-store", "details": {"large": "record"}},
            {"module": "policy-engine"},
        ],
        events=[
            {"contract_id": "EV-001", "event_name": "ranking.completed"},
            {"event_name": "explanation.created"},
        ],
    )

    assert result["interface_refs"] == ["IF-001", "explain"]
    assert result["dependency_refs"] == ["profile-store", "policy-engine"]
    assert result["event_refs"] == ["EV-001", "explanation.created"]
