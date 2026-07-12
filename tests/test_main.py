from pathlib import Path
from unittest.mock import patch, MagicMock

from prd_flow.main import _run_smart_check, _run_ambiguity_check, _resume_session, _check_gherkin_coverage
from prd_flow.quality.suggest import suggest_fix
from prd_flow.quality.smart_req import SMARTResult
from prd_flow.utils import generate_doc_id
from prd_flow.session import SessionState, save_session


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


def test_resume_session_continues_from_partial(tmp_path):
    """Resume from a session where P1 and P2 are completed; P3-P5 should run."""
    session_file = tmp_path / "session.json"
    state = SessionState(
        session_id="sess_abc123",
        mode="root",
        current_phase="P3",
        completed_phases=["P1", "P2"],
        draft_content={
            "P1": {"doc_id": "TEST-PROJECT-v1.0", "version": "1.0.0", "author": "Alice", "priority": "P0"},
            "P2": {"target_users": "developers", "pain_points": "hard to write PRDs", "opportunity": "automated tool"},
        },
    )
    save_session(state, session_file)

    args = MagicMock()
    args.output = str(tmp_path / "output.md")
    args.resume = None

    # Mock inputs:
    # P1 completed -> ask modify -> "n"
    # P2 completed -> ask modify -> "n"
    # P3 (RequirementsPhase.run):
    #   - diverge: "feature1", "done"
    #   - classify priority: "Must Have"
    #   - refine q1,q2,q3: "a", "b", "c"
    #   - NFR: "done"
    # P4 (AcceptancePhase.run):
    #   - scenario name: "done" (skip)
    # P5 (SuccessMetricsPhase.run):
    #   - metric name: "done" (skip)
    # Quality gates run AFTER all phases in _resume_session:
    #   - smart check report, ask continue -> "y"
    #   - final ambiguity report, ask continue -> "y"
    inputs = [
        "n",              # don't modify P1
        "n",              # don't modify P2
        "feature1",       # P3 diverge
        "done",           # end diverge
        "Must Have",      # classify priority
        "a", "b", "c",    # refine questions
        "done",           # NFR done
        "done",           # P4 scenario name -> skip
        "done",           # P5 metric name -> skip
        "y",              # quality gate (smart check) continue
        "y",              # final quality gate (ambiguity) continue
    ]

    with patch("builtins.input", side_effect=inputs):
        with patch("prd_flow.main.assemble_prd", return_value="test prd content"):
            _resume_session(session_file, args)

    output_path = Path(args.output)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "test prd content"

    # Verify session was saved (saved to cwd as .prd_session_{id}.json)
    session_path = Path(f".prd_session_{state.session_id}.json")
    assert session_path.exists()
    # Clean up session file
    session_path.unlink()


def test_resume_session_modifies_completed_phase(tmp_path):
    """Resume and choose to modify a completed phase (P1)."""
    session_file = tmp_path / "session.json"
    state = SessionState(
        session_id="sess_mod123",
        mode="root",
        current_phase="P2",
        completed_phases=["P1"],
        draft_content={
            "P1": {"doc_id": "OLD-PROJECT-v1.0", "version": "1.0.0", "author": "Alice", "priority": "P0"},
        },
    )
    save_session(state, session_file)

    args = MagicMock()
    args.output = str(tmp_path / "output.md")
    args.resume = None

    # Inputs:
    # P1 completed -> ask modify -> "y"
    #   FrontmatterPhase.run: project_name="new project", author="Bob", priority="P1"
    # P2 incomplete -> run automatically
    #   ProblemStatementPhase.run: target_users="users", pain_points="pain", opportunity="opp"
    # P3 run:
    #   diverge: "f1", "done"
    #   classify: "Must Have"
    #   refine: "a", "b", "c"
    #   NFR: "done"
    # P4: scenario name "done"
    # P5: metric name "done"
    # Quality gates run AFTER all phases:
    #   - smart check: "y"
    #   - final ambiguity: "y"
    inputs = [
        "y",              # modify P1
        "new project",    # P1 project name
        "Bob",            # P1 author
        "P1",             # P1 priority
        "users",          # P2 target_users
        "pain",           # P2 pain_points
        "opp",            # P2 opportunity
        "f1",             # P3 diverge
        "done",           # end diverge
        "Must Have",      # classify
        "a", "b", "c",    # refine
        "done",           # NFR done
        "done",           # P4 scenario name -> skip
        "done",           # P5 metric name -> skip
        "y",              # quality gate (smart check)
        "y",              # final quality gate (ambiguity)
    ]

    with patch("builtins.input", side_effect=inputs):
        with patch("prd_flow.main.assemble_prd", return_value="test prd"):
            _resume_session(session_file, args)

    # Load the saved session and verify P1 was updated
    saved_session_path = Path(f".prd_session_{state.session_id}.json")
    from prd_flow.session import load_session
    saved_state = load_session(saved_session_path)
    assert saved_state.draft_content["P1"]["author"] == "Bob"
    assert saved_state.draft_content["P1"]["priority"] == "P1"
    # Clean up session file
    saved_session_path.unlink()


def test_resume_session_all_completed_goes_to_output(tmp_path):
    """Resume a fully completed session; no phases re-run, goes straight to output."""
    session_file = tmp_path / "session.json"
    state = SessionState(
        session_id="sess_done456",
        mode="root",
        current_phase="P5",
        completed_phases=["P1", "P2", "P3", "P4", "P5"],
        draft_content={
            "P1": {"doc_id": "DONE-PROJECT-v1.0", "version": "1.0.0", "author": "Alice", "priority": "P0"},
            "P2": {"target_users": "devs", "pain_points": "pain", "opportunity": "opp"},
            "P3": {
                "functional": [{"id": "REQ-001", "text": "系统应响应 ≤ 200ms", "priority": "Must Have", "gherkin_count": 1}],
                "non_functional": [],
            },
            "P4": {"scenarios": [{"feature": "f", "scenario": "s", "given": "g", "when": "w", "then": "t"}]},
            "P5": {"metrics": [{"name": "m1", "target": "t1", "method": "method1"}]},
        },
    )
    save_session(state, session_file)

    args = MagicMock()
    args.output = str(tmp_path / "output.md")
    args.resume = None

    # Inputs: all "n" for modify questions, then "y" for quality gates
    inputs = [
        "n",  # don't modify P1
        "n",  # don't modify P2
        "n",  # don't modify P3
        "n",  # don't modify P4
        "n",  # don't modify P5
        "y",  # quality gate after P3 (smart check)
        "y",  # final quality gate (ambiguity)
    ]

    with patch("builtins.input", side_effect=inputs):
        with patch("prd_flow.main.assemble_prd", return_value="fully assembled prd"):
            _resume_session(session_file, args)

    output_path = Path(args.output)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "fully assembled prd"


def test_suggest_fix_for_specific_failure():
    req = {"id": "REQ-001", "text": "系统应该很快"}
    result = SMARTResult(req_id="REQ-001", specific=False, measurable=True, testable=True)
    fix = suggest_fix(req, result)
    assert "模糊量词" in fix
    assert "很快" in fix


def test_suggest_fix_for_measurable_failure():
    req = {"id": "REQ-002", "text": "支持用户注册"}
    result = SMARTResult(req_id="REQ-002", specific=True, measurable=False, testable=True)
    fix = suggest_fix(req, result)
    assert "已授权的指标" in fix


def test_suggest_fix_for_testable_failure():
    req = {"id": "REQ-003", "text": "支持并发", "priority": "Must Have", "gherkin_count": 0}
    result = SMARTResult(req_id="REQ-003", specific=True, measurable=True, testable=False)
    fix = suggest_fix(req, result)
    assert "Gherkin" in fix


def test_check_gherkin_coverage_finds_gap():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P4",
        completed_phases=["P1", "P2", "P3"],
        draft_content={
            "P3": {
                "functional": [
                    {"id": "REQ-001", "text": "支持注册", "priority": "Must Have", "gherkin_count": 0},
                    {"id": "REQ-002", "text": "支持登录", "priority": "Should Have", "gherkin_count": 0},
                ],
                "non_functional": [],
            },
            "P4": {
                "scenarios": [
                    {"feature": "登录", "scenario": "用户登录", "given": "...", "when": "...", "then": "..."},
                ]
            },
        },
    )
    gaps = _check_gherkin_coverage(state)
    assert len(gaps) == 1
    assert gaps[0]["id"] == "REQ-001"


def test_check_gherkin_coverage_passes_when_gherkin_count_present():
    state = SessionState(
        session_id="sess_001",
        mode="root",
        current_phase="P4",
        completed_phases=["P1", "P2", "P3"],
        draft_content={
            "P3": {
                "functional": [
                    {"id": "REQ-001", "text": "支持注册", "priority": "Must Have", "gherkin_count": 2},
                ],
                "non_functional": [],
            },
            "P4": {"scenarios": []},
        },
    )
    gaps = _check_gherkin_coverage(state)
    assert len(gaps) == 0
