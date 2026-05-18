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
