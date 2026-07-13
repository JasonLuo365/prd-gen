from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.session import SessionState


def test_collect_adds_metric_id_and_traceability_container():
    state = SessionState(session_id="x", mode="root", current_phase="P5", completed_phases=[], draft_content={})
    result = SuccessMetricsPhase(state).collect([{"name": "latency", "target": "<= 3s", "method": "eval set"}])
    assert result["metrics"][0]["id"] == "METRIC-001"
    assert result["metrics"][0]["verifies"] == []
