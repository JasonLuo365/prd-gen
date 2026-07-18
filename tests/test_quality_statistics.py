"""Regression coverage for non-placeholder PRD quality statistics."""
from __future__ import annotations

from argparse import Namespace

from prd_flow.main import _quality_statistics
from prd_flow.session import SessionState


def test_quality_statistics_counts_evidence_unknown_references_and_conflicting_responses() -> None:
    state = SessionState(
        session_id="statistics", mode="root", current_phase="complete", completed_phases=[],
        draft_content={
            "P3": {"functional": [
                {"id": "REQ-001", "text": "Record request", "evidence_refs": ["decision:1"]},
                {"id": "REQ-002", "text": "Show status", "evidence_refs": []},
            ], "non_functional": []},
            "P4": {"contracts": [
                {"id": "AC-001", "type": "functional", "verifies": ["REQ-001"], "response": ["accepted"]},
                {"id": "AC-001", "type": "functional", "verifies": ["REQ-404"], "response": ["rejected"]},
            ]},
            "P5": {"metrics": []},
        },
    )
    statistics = _quality_statistics(state)
    assert statistics["evidence_backed_requirement_count"] == 1
    assert statistics["evidence_coverage_ratio"] == 0.5
    assert statistics["unknown_reference_count"] == 1
    assert statistics["conflicting_response_count"] == 1
