from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.session import SessionState


def test_success_metrics_phase_collects_data():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P5",
        completed_phases=[],
        draft_content={},
    )
    phase = SuccessMetricsPhase(state)

    result = phase.collect(
        metrics=[
            {"name": "注册转化率", "target": "≥ 70%", "method": "埋点统计"},
        ],
    )

    assert len(result["metrics"]) == 1
    assert result["metrics"][0]["name"] == "注册转化率"
    assert result["metrics"][0]["target"] == "≥ 70%"
    assert state.draft_content["P5"] == result
    assert "P5" in state.completed_phases
