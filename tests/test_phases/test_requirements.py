from unittest.mock import patch

from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.session import SessionState


def test_requirements_phase_collects_data():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    result = phase.collect(
        functional=[
            {"id": "REQ-001", "text": "支持邮箱注册", "priority": "Must Have", "gherkin_count": 2},
        ],
        non_functional=[
            {"id": "NFR-001", "text": "可用性 ≥ 99.9%"},
        ],
    )

    assert len(result["functional"]) == 1
    assert result["functional"][0]["id"] == "REQ-001"
    assert result["functional"][0]["priority"] == "Must Have"
    assert result["functional"][0]["gherkin_count"] == 2
    assert len(result["non_functional"]) == 1
    assert result["non_functional"][0]["id"] == "NFR-001"
    assert state.draft_content["P3"] == result
    assert "P3" in state.completed_phases


def test_requirements_phase_run_interactive():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    # Step 1: Diverge - two features
    # Step 2: Classify - priorities for each
    # Step 3: Refine - only Must Have gets 3 questions (each Must Have gets 3 questions)
    # Step 4: Non-functional - one NFR
    inputs = [
        "用户可以注册和登录",
        "用户可以下单购买",
        "done",
        "Must Have",
        "Must Have",
        "邮箱、手机号注册和登录",
        "重复注册、密码错误",
        "密码需8位以上，登录响应≤100ms",
        "邮箱、手机号下单购买",
        "库存不足、支付失败",
        "下单响应≤200ms",
        "NFR-001",
        "并发用户数 ≥ 1000",
        "done",
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["functional"]) == 2
    assert result["functional"][0]["id"] == "REQ-001"
    assert result["functional"][0]["priority"] == "Must Have"
    assert result["functional"][0]["gherkin_count"] == 1
    assert "用户可以注册和登录" in result["functional"][0]["text"]
    assert result["functional"][1]["id"] == "REQ-002"
    assert result["functional"][1]["priority"] == "Must Have"
    assert result["functional"][1]["gherkin_count"] == 1
    assert len(result["non_functional"]) == 1
    assert result["non_functional"][0]["id"] == "NFR-001"
    assert result["non_functional"][0]["text"] == "并发用户数 ≥ 1000"


def test_requirements_phase_run_interactive_refines_must_have():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    # Step 1: Two features
    # Step 2: One Must Have, one Could Have
    # Step 3: Only Must Have gets refined
    # Step 4: No non-functional requirements
    inputs = [
        "用户可以注册和登录",
        "系统支持深色模式",
        "done",
        "Must Have",
        "Could Have",
        "邮箱、手机号注册和登录",
        "重复注册、密码错误",
        "密码需8位以上，登录响应≤100ms",
        "done",
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["functional"]) == 2

    # Must Have should be refined
    must_have = result["functional"][0]
    assert must_have["id"] == "REQ-001"
    assert must_have["priority"] == "Must Have"
    assert must_have["gherkin_count"] == 1
    assert "用户可以注册和登录" in must_have["text"]
    assert "邮箱、手机号注册和登录" in must_have["text"]
    assert "重复注册、密码错误" in must_have["text"]
    assert "密码需8位以上，登录响应≤100ms" in must_have["text"]

    # Could Have should NOT be refined
    could_have = result["functional"][1]
    assert could_have["id"] == "REQ-002"
    assert could_have["priority"] == "Could Have"
    assert could_have["gherkin_count"] == 0
    assert could_have["text"] == "系统支持深色模式"

    assert len(result["non_functional"]) == 0


def test_requirements_phase_auto_assigns_nfr_id():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=[],
        draft_content={},
    )
    phase = RequirementsPhase(state)

    # Step 1: No functional requirements (only "done" needed)
    # Step 2: No priorities (loop skipped when no features)
    # Step 3: No refinement (loop skipped when no Must-Have features)
    # Step 4: Two NFRs, second with auto-assigned ID
    inputs = [
        "done",
        "NFR-001",
        "并发用户数 ≥ 1000",
        "",
        "可用性 ≥ 99.9%",
        "done",
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["non_functional"]) == 2
    assert result["non_functional"][0]["id"] == "NFR-001"
    assert result["non_functional"][1]["id"] == "NFR-002"
    assert result["non_functional"][1]["text"] == "可用性 ≥ 99.9%"
