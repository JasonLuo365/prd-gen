import tempfile
from pathlib import Path

from prd_flow.derive.parser import extract_architecture_catalog, extract_module_context, parse_parent_prd


def test_parse_parent_prd():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## Must Have
- [REQ-005] 系统应支持多种支付方式
- [REQ-006] 支付流程应在3秒内完成
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(prd_content)
        f.flush()
        path = Path(f.name)

    try:
        result = parse_parent_prd(path)
        assert result["doc_id"] == "PARENT-v1.0"
        assert len(result["requirements"]) == 2
        assert result["requirements"][0]["id"] == "REQ-005"
        assert result["requirements"][0]["priority"] == "Must Have"
    finally:
        path.unlink()


def test_parse_parent_prd_preserves_moscow_priority_and_nfrs():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-001] 必须支持手机号登录

### Should Have
- [REQ-002] 应支持登录审计

### Could Have
- [REQ-003] 可支持登录风险分析

## 非功能需求
- [NFR-001] 登录接口 P95 <= 2 秒
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(prd_content)
        f.flush()
        path = Path(f.name)

    try:
        result = parse_parent_prd(path)
        priorities = {req["id"]: req["priority"] for req in result["requirements"]}
        assert priorities == {
            "REQ-001": "Must Have",
            "REQ-002": "Should Have",
            "REQ-003": "Could Have",
        }
        assert result["non_functional"] == [
            {"id": "NFR-001", "text": "登录接口 P95 <= 2 秒"}
        ]
    finally:
        path.unlink()


def test_parse_parent_prd_preserves_tagged_gherkin_steps(tmp_path: Path):
    path = tmp_path / "prd.md"
    path.write_text(
        """# Requirements

### Must Have
- [REQ-002] 前端和后端都必须限制图片数量。

# Acceptance

```gherkin
Feature: 图片数量限制
  @REQ-002
  Scenario: 第四张图片被前端阻止
    Given 学生已选择 3 张图片
    When 学生添加第 4 张图片
    Then 前端不允许继续添加图片
    And 后端不会收到第四张图片
```
""",
        encoding="utf-8",
    )

    result = parse_parent_prd(path)

    scenario = result["acceptance_scenarios"][0]
    assert scenario["requirement_ids"] == ["REQ-002"]
    assert scenario["steps"][-2:] == [
        {"keyword": "Then", "text": "前端不允许继续添加图片"},
        {"keyword": "And", "text": "后端不会收到第四张图片"},
    ]


def test_parse_parent_prd_preserves_derive_requirement_metadata(tmp_path: Path):
    path = tmp_path / "derived.md"
    path.write_text(
        """# Requirements

### Must Have
- [REQ-A001] 模块必须提供上传接口。
  - parent_req: ARCH:06-interface-contracts.md#UPLOAD
  - implementation_surfaces: [api_backend, database_migration]
  - related_reqs: [REQ-D001, REQ-D002]
  - evidence_refs: [DEC-001, parent:REQ-001]
  - source_kind: architecture_interface
""",
        encoding="utf-8",
    )

    requirement = parse_parent_prd(path)["requirements"][0]

    assert requirement["source_kind"] == "architecture_interface"
    assert requirement["parent_req"] == "ARCH:06-interface-contracts.md#UPLOAD"
    assert requirement["implementation_surfaces"] == ["api_backend", "database_migration"]
    assert requirement["related_reqs"] == ["REQ-D001", "REQ-D002"]
    assert requirement["evidence_refs"] == ["DEC-001", "parent:REQ-001"]


def test_parse_parent_prd_preserves_success_metrics(tmp_path: Path):
    path = tmp_path / "metrics.md"
    path.write_text(
        """# Success Metrics

| 指标 | 目标值 | 测量方式 |
|---|---|---|
| MET-001 首轮提示成功率 | >= 95% | 从提示请求开始，到提示展示结束。 |

## 不涉及 / Non-goals
- 当前版本不支持视频题目输入。
""",
        encoding="utf-8",
    )

    metrics = parse_parent_prd(path)["success_metrics"]

    assert metrics == [
        {
            "id": "MET-001",
            "name": "MET-001 首轮提示成功率",
            "target": ">= 95%",
            "method": "从提示请求开始，到提示展示结束。",
        }
    ]
    assert parse_parent_prd(path)["non_goals"] == ["当前版本不支持视频题目输入。"]


def test_parse_parent_prd_without_frontmatter():
    """没有 frontmatter 时也能正常解析。"""
    prd_content = "# Requirements\n\n## Must Have\n- [REQ-001] 基本功能\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(prd_content)
        f.flush()
        path = Path(f.name)

    try:
        result = parse_parent_prd(path)
        assert result["doc_id"] == "UNKNOWN"
        assert len(result["requirements"]) == 1
        assert result["requirements"][0]["id"] == "REQ-001"
    finally:
        path.unlink()


def test_parse_parent_prd_with_malformed_frontmatter():
    """frontmatter 只有一对分隔符时不崩溃。"""
    prd_content = "---\n仅有一个分隔符\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(prd_content)
        f.flush()
        path = Path(f.name)

    try:
        result = parse_parent_prd(path)
        assert result["doc_id"] == "UNKNOWN"
    finally:
        path.unlink()


def test_extract_module_context():
    arch_content = """
modules:
  - name: payment_gateway
    interfaces:
      - name: create_payment
        method: POST
        path: /api/v1/payments
  - name: user_service
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(arch_content)
        f.flush()
        path = Path(f.name)

    try:
        result = extract_module_context(path, "payment_gateway")
        assert result["found"] is True
        assert result["module"]["name"] == "payment_gateway"
        assert len(result["module"]["interfaces"]) == 1
    finally:
        path.unlink()


def test_extract_missing_module():
    arch_content = "modules:\n  - name: user_service\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(arch_content)
        f.flush()
        path = Path(f.name)

    try:
        result = extract_module_context(path, "payment_gateway")
        assert result["found"] is False
        assert result["available_modules"] == ["user_service"]
    finally:
        path.unlink()


def test_extract_module_from_empty_file():
    """空文件时返回空列表。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        path = Path(f.name)

    try:
        result = extract_module_context(path, "any_module")
        assert result["found"] is False
        assert result["available_modules"] == []
    finally:
        path.unlink()


def test_extract_module_from_invalid_yaml():
    """YAML 解析结果不是字典时不崩溃。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("just_a_string")
        f.flush()
        path = Path(f.name)

    try:
        result = extract_module_context(path, "any_module")
        assert result["found"] is False
        assert result["available_modules"] == []
    finally:
        path.unlink()


def test_parse_parent_prd_extracts_acceptance_contracts(tmp_path):
    parent = tmp_path / "parent.md"
    parent.write_text(
        """# Requirements
## Current Release — Functional Requirements
### Must Have
- [REQ-001] Rank Amazon products
  - release_scope: current
  - requirement_kind: atomic

# Acceptance Contracts
## AC-REQ-001-01
- type: functional
- verifies: [REQ-001]
- release_scope: current
- actor: shopper
- preconditions: purchase history exists
- trigger: asks for a recommendation
- response: ranked Amazon products
- observable_oracles: order is displayed
- boundaries: no target-domain history -> cross-domain profile
- exceptions: Amazon API unavailable -> failure is displayed
- evidence_refs: owner-decision-1
""",
        encoding="utf-8",
    )
    parsed = parse_parent_prd(parent)
    assert parsed["requirements"][0]["release_scope"] == "current"
    assert parsed["requirements"][0]["requirement_kind"] == "atomic"
    assert parsed["acceptance_contracts"][0]["verifies"] == ["REQ-001"]
    assert parsed["acceptance_contracts"][0]["response"] == ["ranked Amazon products"]
    assert parsed["acceptance_contracts"][0]["boundaries"] == [
        {"condition": "no target-domain history", "response": "cross-domain profile"}
    ]


def test_parse_parent_prd_extracts_derived_acceptance_contract_ids(tmp_path):
    parent = tmp_path / "parent.md"
    parent.write_text(
        """# Acceptance Contracts
## D-AC-004
- type: functional
- verifies: [REQ-D004]
- trigger: resolve candidates
- response: candidates returned
- observable_oracles: candidate list is visible

## D-AC-NFR-001
- type: non_functional
- verifies: [NFR-D001]
- trigger: measure latency
- response: latency is recorded
- observable_oracles: P95 is within target
""",
        encoding="utf-8",
    )

    contracts = parse_parent_prd(parent)["acceptance_contracts"]

    assert [contract["id"] for contract in contracts] == ["D-AC-004", "D-AC-NFR-001"]


def test_parse_acceptance_contract_preserves_semicolon_actions_in_one_response(tmp_path):
    parent = tmp_path / "parent.md"
    parent.write_text(
        """# Acceptance Contracts
## AC-004 Amazon candidates
- verifies: [REQ-004]
- boundaries: more than 50 candidates or missing fields -> process only the first 50; retain unverifiable candidates with a warning
""",
        encoding="utf-8",
    )

    parsed = parse_parent_prd(parent)

    assert parsed["acceptance_contracts"][0]["boundaries"] == [
        {
            "condition": "more than 50 candidates or missing fields",
            "response": "process only the first 50; retain unverifiable candidates with a warning",
        }
    ]


def test_recursive_architecture_package_exposes_direct_children_and_derived_refs(tmp_path):
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "architecture-manifest.yaml").write_text(
        "artifact_inventory:\n  - 02-architecture-decomposition.md\n  - 03-state-and-data.md\n  - 04-contracts-and-runtime.md\n",
        encoding="utf-8",
    )
    (architecture / "01-design-context.md").write_text(
        "| Requirement | Disposition |\n|---|---|\n| REQ-D099 | out-of-scope |\n",
        encoding="utf-8",
    )
    (architecture / "02-architecture-decomposition.md").write_text(
        """# Architecture decomposition
| child_id | 责任与所有权 | 排除 | 需求 | 依赖与存在理由 |
|---|---|---|---|---|
| `query-resolution` | 解析查询并拥有 QueryState。 | 不调用外部服务。 | D001~D003、NFR-D001 | profile；独立生命周期。 |
| `candidate-workset` | 拥有候选工作集。 | 不负责排序。 | REQ-D004/D006-D008 | query；独立状态。 |
""",
        encoding="utf-8",
    )
    (architecture / "03-state-and-data.md").write_text(
        """# State and data
| 状态 | Owner child_id | 读者 | 生命周期 |
|---|---|---|---|
| `QueryState` | `query-resolution` | candidate-workset | request |
""",
        encoding="utf-8",
    )
    (architecture / "04-contracts-and-runtime.md").write_text(
        """# Contracts
```yaml
contract_id: query.resolved.v1
owner: query-resolution
consumer: candidate-workset
required_fields: [request_id, raw_query]
produced_fields: [request_id, semantic_query]
error_codes: [query_invalid]
```
""",
        encoding="utf-8",
    )

    catalog = extract_architecture_catalog(architecture, "component")

    assert [unit["name"] for unit in catalog["units"]] == [
        "query-resolution",
        "candidate-workset",
    ]
    query, candidates = catalog["units"]
    assert query["requirement_refs"] == ["REQ-D001", "REQ-D002", "REQ-D003", "NFR-D001"]
    assert candidates["requirement_refs"] == [
        "REQ-D004",
        "REQ-D006",
        "REQ-D007",
        "REQ-D008",
    ]
    assert query["interfaces"][0]["contract_id"] == "query.resolved.v1"
    assert candidates["interfaces"][0]["ownership_role"] == "consumer"
    assert query["data_assets"][0]["name"] == "QueryState"
    assert catalog["excluded_requirement_refs"] == ["REQ-D099"]
