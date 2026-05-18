from prd_flow.main import _run_smart_check, _run_ambiguity_check
from prd_flow.utils import generate_doc_id
from prd_flow.session import SessionState


def test_generate_doc_id():
    assert generate_doc_id("my project") == "MY-PROJECT-v1.0"
    assert generate_doc_id("ecommerce_platform") == "ECOMMERCE-PLATFORM-v1.0"


def test_run_smart_check():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P3",
        completed_phases=["P1", "P2"],
        draft_content={
            "P3": {
                "functional": [
                    {"id": "REQ-001", "text": "响应时间 ≤ 200ms", "priority": "Must Have", "gherkin_count": 1},
                    {"id": "REQ-002", "text": "系统应该很快", "priority": "Must Have", "gherkin_count": 0},
                ],
                "non_functional": [],
            }
        },
    )
    results = _run_smart_check(state)
    assert len(results) == 2
    assert results[0].overall_pass is True
    assert results[1].overall_pass is False


def test_run_ambiguity_check():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P5",
        completed_phases=[],
        draft_content={
            "P3": {
                "functional": [
                    {"id": "REQ-001", "text": "用户可注册", "priority": "Must Have", "gherkin_count": 1},
                ],
                "non_functional": [],
            }
        },
    )
    prd_text = "用户可以通过邮箱注册。管理员可以审核用户。"
    result = _run_ambiguity_check(state, prd_text)
    assert "lexical" in result
    assert "logic" in result
    assert "completeness" in result
