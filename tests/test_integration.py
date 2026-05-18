"""End-to-end integration test for PRD generation workflow."""
from pathlib import Path
import tempfile

from prd_flow.output.assembler import assemble_prd
from prd_flow.phases.frontmatter import FrontmatterPhase
from prd_flow.phases.problem_statement import ProblemStatementPhase
from prd_flow.phases.requirements import RequirementsPhase
from prd_flow.phases.acceptance import AcceptancePhase
from prd_flow.phases.success_metrics import SuccessMetricsPhase
from prd_flow.main import _run_smart_check, _run_ambiguity_check
from prd_flow.quality.ambiguity import scan_ambiguity
from prd_flow.quality.smart_req import check_smart_req
from prd_flow.session import SessionState


def test_end_to_end_root_prd_generation():
    """Test complete flow: collect data → quality check → assemble."""
    state = SessionState(
        session_id="sess_test_001",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
    )

    # Phase 1: Frontmatter
    phase1 = FrontmatterPhase(state)
    phase1.collect(project_name="ecommerce_platform", author="test", priority="P0")
    assert "P1" in state.completed_phases
    assert state.draft_content["P1"]["doc_id"] == "ECOMMERCE-PLATFORM-v1.0"

    # Phase 2: Problem Statement
    phase2 = ProblemStatementPhase(state)
    phase2.collect(
        target_users="电商消费者",
        pain_points="结账流程繁琐",
        opportunity="一键支付",
    )
    assert "P2" in state.completed_phases

    # Phase 3: Requirements
    phase3 = RequirementsPhase(state)
    phase3.collect(
        functional=[
            {
                "id": "REQ-001",
                "text": "支持邮箱注册，密码需包含8位以上字母数字组合",
                "priority": "Must Have",
                "gherkin_count": 2,
            },
            {
                "id": "REQ-002",
                "text": "系统响应时间 ≤ 200ms",
                "priority": "Must Have",
                "gherkin_count": 1,
            },
        ],
        non_functional=[
            {"id": "NFR-001", "text": "可用性 ≥ 99.9%"},
        ],
    )
    assert "P3" in state.completed_phases

    # Quality gate after P3
    smart_results = _run_smart_check(state)
    assert len(smart_results) == 2
    assert all(r.overall_pass for r in smart_results)

    # Phase 4: Acceptance
    phase4 = AcceptancePhase(state)
    phase4.collect(
        scenarios=[
            {
                "feature": "用户注册",
                "scenario": "通过邮箱成功注册",
                "given": "用户访问注册页面",
                "when": "用户输入有效邮箱和密码",
                "then": "账户创建成功",
            },
        ]
    )
    assert "P4" in state.completed_phases

    # Phase 5: Success Metrics
    phase5 = SuccessMetricsPhase(state)
    phase5.collect(
        metrics=[
            {"name": "注册转化率", "target": "≥ 70%", "method": "埋点统计"},
        ]
    )
    assert "P5" in state.completed_phases

    # Assemble
    prd = assemble_prd(state.draft_content)
    assert "ECOMMERCE-PLATFORM-v1.0" in prd
    assert "```gherkin" in prd
    assert "电商消费者" in prd
    assert "REQ-001" in prd
    assert "注册转化率" in prd

    # Final ambiguity check
    ambiguity = _run_ambiguity_check(state, prd)
    assert "lexical" in ambiguity
    assert "logic" in ambiguity
    assert "completeness" in ambiguity


def test_quality_gate_blocks_poor_requirements():
    """质量门控能识别不满足SMART-REQ的需求。"""
    state = SessionState(
        session_id="sess_test_002",
        mode="root",
        current_phase="P3",
        completed_phases=["P1", "P2"],
        draft_content={
            "P3": {
                "functional": [
                    {"id": "REQ-BAD", "text": "系统应该很快", "priority": "Must Have", "gherkin_count": 0},
                ],
                "non_functional": [],
            }
        },
    )

    smart_results = _run_smart_check(state)
    assert len(smart_results) == 1
    assert smart_results[0].overall_pass is False
    assert smart_results[0].specific is False
    assert smart_results[0].measurable is False
    assert smart_results[0].testable is False
