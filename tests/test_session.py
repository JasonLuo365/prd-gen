import json
import tempfile
from pathlib import Path

from prd_flow.session import SessionState, save_session, load_session


def test_save_and_load_session():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={},
        parent_context=None,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "session.json"
        save_session(state, path)
        loaded = load_session(path)

    assert loaded.session_id == "sess_001"
    assert loaded.mode == "root"
    assert loaded.current_phase == "P1"


def test_save_and_load_with_unicode():
    """编码一致性：非ASCII字符能正确保存和加载。"""
    state = SessionState(
        session_id="sess_002",
        mode="root",
        current_phase="P1",
        completed_phases=[],
        draft_content={"project_name": "电商平台", "description": "支持多种支付方式"},
        parent_context=None,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "session.json"
        save_session(state, path)
        loaded = load_session(path)

    assert loaded.draft_content["project_name"] == "电商平台"
    assert loaded.draft_content["description"] == "支持多种支付方式"
