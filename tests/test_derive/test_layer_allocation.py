from pathlib import Path

from prd_flow.derive.layer_allocation import build_layer_allocation


def test_layer_allocation_covers_all_parent_obligations_without_a_must_budget(tmp_path: Path):
    parent = tmp_path / "parent.md"
    parent.write_text(
        """---
doc_id: ROOT-001
---
# Current Release — Functional Requirements
## REQ-001 用户画像
- priority: Must Have
- release_scope: current
- evidence_refs: [DEC-001]
| Clause ID | Normative behavior |
|---|---|
| CLAUSE-001-01 | 系统生成用户画像。 |
| CLAUSE-001-02 | 系统保存画像版本。 |

## REQ-002 查询编排
- priority: Must Have
- release_scope: current
- evidence_refs: [DEC-002]
| Clause ID | Normative behavior |
|---|---|
| CLAUSE-002-01 | 系统理解用户查询。 |

# Current Release — Non-functional Requirements
| ID | Requirement | Release scope | Evidence |
|---|---|---|---|
| NFR-001 | 请求必须在 10 秒内完成。 | current | DEC-003 |

# Success Metrics
| ID | Metric | Target | Measurement | Verifies |
|---|---|---|---|---|
| METRIC-001 | 画像成功率 | 100% | 检查全部画像请求 | REQ-001 |

# Acceptance Contracts
## AC-001 画像契约
- type: functional
- verifies: [CLAUSE-001-01, CLAUSE-001-02]
- release_scope: current
- actor: user
- preconditions: [authorized]
- trigger: request profile
- response: [profile generated]
- observable_oracles: [profile and version visible]
- boundaries: no evidence -> empty profile
- exceptions: storage unavailable -> request fails
- evidence_refs: [DEC-001]
## AC-002 查询契约
- type: functional
- verifies: [CLAUSE-002-01]
- release_scope: current
- actor: user
- preconditions: [query exists]
- trigger: submit query
- response: [query interpreted]
- observable_oracles: [interpretation visible]
- boundaries: empty query -> rejected
- exceptions: parser unavailable -> request fails
- evidence_refs: [DEC-002]
## AC-NFR-001 时延契约
- type: nfr
- verifies: [NFR-001]
- release_scope: current
- population: all requests
- measurement_start: request accepted
- measurement_end: result visible
- unit: seconds
- threshold: <= 10
- exclusions: [none]
- pass_rule: every request passes
- evidence_refs: [DEC-003]
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "01-system-overview.md").write_text(
        """# System Overview
| Module | Responsibility | Owns / Controls | Primary Source |
|---|---|---|---|
| Profile Intelligence | 用户画像与画像版本 | profile | FR-001 |
| Query Orchestration | 用户查询理解与编排 | query | FR-002 |
""",
        encoding="utf-8",
    )

    result = build_layer_allocation(parent, architecture, "deployable_module")

    assert result["success"] is True
    assert result["target_modules"] == ["Profile Intelligence", "Query Orchestration"]
    assert all(row["status"] == "allocated" for row in result["ledger"])
    profile_ids = {
        item["id"]
        for item in result["contexts"]["Profile Intelligence"]["related_requirements"]
    }
    assert profile_ids == {"CLAUSE-001-01", "CLAUSE-001-02"}


def test_layer_allocation_supports_recursive_l1_architecture_packages():
    root = Path(__file__).resolve().parents[2] / "outputs" / "user-side-personal-recommendation-assistant"
    expected_children = {
        "L1-amazon-acl": 5,
        "L1-configuration-governance": 3,
        "L1-privacy-lifecycle": 5,
        "L1-profile-intelligence": 4,
        "L1-recommendation-orchestration": 5,
    }

    for node_name, child_count in expected_children.items():
        node = root / "L1" / node_name
        result = build_layer_allocation(node / "prd.md", node / "architecture", "component")

        assert result["success"] is True, (node_name, result["errors"])
        assert result["coverage_complete"] is True
        assert len(result["target_modules"]) == child_count
