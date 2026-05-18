from unittest.mock import patch

from prd_flow.phases.problem_statement import ProblemStatementPhase
from prd_flow.session import SessionState


def test_problem_statement_phase_collects_data():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P2",
        completed_phases=[],
        draft_content={},
    )
    phase = ProblemStatementPhase(state)

    result = phase.collect(
        target_users="电商消费者",
        pain_points="结账流程繁琐",
        opportunity="一键支付",
    )

    assert result["target_users"] == "电商消费者"
    assert result["pain_points"] == "结账流程繁琐"
    assert result["opportunity"] == "一键支付"
    assert state.draft_content["P2"] == result
    assert "P2" in state.completed_phases


def test_problem_statement_phase_run_interactive():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P2",
        completed_phases=[],
        draft_content={},
    )
    phase = ProblemStatementPhase(state)

    with patch("builtins.input", side_effect=["开发者", "文档难写", "自动化工具"]):
        result = phase.run()

    assert result["target_users"] == "开发者"
    assert result["pain_points"] == "文档难写"
    assert result["opportunity"] == "自动化工具"
