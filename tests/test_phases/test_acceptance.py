from unittest.mock import patch

from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.session import SessionState


def test_acceptance_phase_collects_data():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P4",
        completed_phases=[],
        draft_content={},
    )
    phase = AcceptancePhase(state)

    result = phase.collect(
        scenarios=[
            {
                "feature": "用户注册",
                "scenario": "通过邮箱成功注册",
                "given": "用户访问注册页面",
                "when": "用户输入有效邮箱和密码",
                "then": "账户创建成功",
            },
        ],
    )

    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["feature"] == "用户注册"
    assert result["scenarios"][0]["given"] == "用户访问注册页面"
    assert state.draft_content["P4"] == result
    assert "P4" in state.completed_phases


def test_acceptance_phase_run_interactive():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P4",
        completed_phases=[],
        draft_content={},
    )
    phase = AcceptancePhase(state)

    # New guided flow inputs:
    # scenario name, feature name (default), given, when, then, confirm, done
    inputs = [
        "用户成功注册", "",  # scenario name, feature default
        "用户未登录且访问注册页面",  # given
        "输入有效邮箱和密码",  # when (no comma)
        "创建未验证账户并发送验证邮件",  # then
        "y",  # confirm
        "done",  # done
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["feature"] == "通用功能"
    assert result["scenarios"][0]["scenario"] == "用户成功注册"
    assert result["scenarios"][0]["given"] == "用户未登录且访问注册页面"
    assert result["scenarios"][0]["when"] == "输入有效邮箱和密码"
    assert result["scenarios"][0]["then"] == "创建未验证账户并发送验证邮件"
    assert "and_steps" not in result["scenarios"][0]


def test_acceptance_phase_run_interactive_with_and_steps():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P4",
        completed_phases=[],
        draft_content={},
    )
    phase = AcceptancePhase(state)

    # Guided flow with comma-separated operation
    inputs = [
        "用户成功注册", "用户注册",  # scenario name, feature name
        "用户未登录且访问注册页面",  # given
        "输入有效邮箱和密码，点击注册按钮",  # when (with comma)
        "创建未验证账户并发送验证邮件",  # then
        "y",  # confirm
        "done",  # done
    ]
    with patch("builtins.input", side_effect=inputs):
        result = phase.run()

    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["feature"] == "用户注册"
    assert result["scenarios"][0]["scenario"] == "用户成功注册"
    assert result["scenarios"][0]["given"] == "用户未登录且访问注册页面"
    assert result["scenarios"][0]["when"] == "输入有效邮箱和密码"
    assert result["scenarios"][0]["and_steps"] == ["点击注册按钮"]
    assert result["scenarios"][0]["then"] == "创建未验证账户并发送验证邮件"
