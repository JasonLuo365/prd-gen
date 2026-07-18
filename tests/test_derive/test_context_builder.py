import tempfile
from pathlib import Path

from prd_flow.derive.context_builder import build_derive_context


def test_build_derive_context_success():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## Must Have
- [REQ-005] payment_gateway 应支持多种支付方式
- [REQ-006] 支付流程应在3秒内完成
- [REQ-007] user_service 应提供用户认证
"""

    arch_content = """
doc_id: "PARENT-ARCH-v1.0"
modules:
  - name: payment_gateway
    interfaces:
      - name: create_payment
        method: POST
        path: /api/v1/payments
    dependencies:
      - name: order_module
        type: upstream
      - name: stripe_api
        type: external
  - name: user_service
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as prd_f, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as arch_f:
        prd_f.write(prd_content)
        arch_f.write(arch_content)
        prd_f.flush()
        arch_f.flush()
        prd_path = Path(prd_f.name)
        arch_path = Path(arch_f.name)

    try:
        result = build_derive_context(prd_path, arch_path, "payment_gateway")
        assert result["success"] is True
        assert result["parent_doc_id"] == "PARENT-v1.0"
        assert result["parent_arch_id"] == "PARENT-ARCH-v1.0"
        assert result["module_name"] == "payment_gateway"
        assert len(result["interfaces"]) == 1
        assert result["interfaces"][0]["name"] == "create_payment"
        assert len(result["dependencies"]) == 2
        # REQ-005 包含 payment_gateway，REQ-006 也包含 payment（模糊匹配）
        assert len(result["related_requirements"]) >= 1
        assert result["error"] is None
    finally:
        prd_path.unlink()
        arch_path.unlink()


def test_build_derive_context_module_not_found():
    prd_content = "---\ndoc_id: PARENT-v1.0\n---\n"
    arch_content = "modules:\n  - name: user_service\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as prd_f, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as arch_f:
        prd_f.write(prd_content)
        arch_f.write(arch_content)
        prd_f.flush()
        arch_f.flush()
        prd_path = Path(prd_f.name)
        arch_path = Path(arch_f.name)

    try:
        result = build_derive_context(prd_path, arch_path, "payment_gateway")
        assert result["success"] is False
        assert "不存在" in result["error"]
        assert result["available_modules"] == ["user_service"]
    finally:
        prd_path.unlink()
        arch_path.unlink()


def test_success_metric_follows_derived_nfr_parent_reference(tmp_path):
    prd = tmp_path / "prd.md"
    prd.write_text(
        """---
doc_id: PARENT-v1.0
---
# Requirements
## Current Release — Functional Requirements
### Must Have
- [REQ-D001] alpha returns ranked results
  - parent_req: CLAUSE-003-01

## Current Release — Non-functional Requirements
- [NFR-D001] alpha latency must be at most 3 seconds
  - parent_nfr: NFR-001

# Success Metrics
| ID | Name | Target | Method | Verifies |
|---|---|---|---|---|
| METRIC-001 | alpha latency | <=3 seconds | measure alpha requests | NFR-001 |
| METRIC-002 | alpha ranking | >=95% | measure alpha rankings | REQ-003 |
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture.yaml"
    architecture.write_text(
        """doc_id: PARENT-ARCH-v1.0
modules:
  - name: alpha
  - name: beta
""",
        encoding="utf-8",
    )

    alpha = build_derive_context(prd, architecture, "alpha")
    beta = build_derive_context(prd, architecture, "beta")

    assert [metric["id"] for metric in alpha["related_success_metrics"]] == [
        "METRIC-001",
        "METRIC-002",
    ]
    assert beta["related_success_metrics"] == []


def test_build_derive_context_detects_orphan_requirements():
    """Requirements mentioning no module should appear in orphan_requirements."""
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## Must Have
- [REQ-001] payment_gateway 应支持多种支付方式
- [REQ-010] 支付退款
- [REQ-011] 用户数据隐私保护
"""

    arch_content = """
doc_id: "PARENT-ARCH-v1.0"
modules:
  - name: payment_gateway
    interfaces:
      - name: create_payment
        method: POST
    dependencies: []
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as prd_f, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as arch_f:
        prd_f.write(prd_content)
        arch_f.write(arch_content)
        prd_f.flush()
        arch_f.flush()
        prd_path = Path(prd_f.name)
        arch_path = Path(arch_f.name)

    try:
        result = build_derive_context(prd_path, arch_path, "payment_gateway")
        assert result["success"] is True
        assert len(result["orphan_requirements"]) >= 2
        orphan_ids = {req.get("id", "") for req in result["orphan_requirements"]}
        assert "REQ-010" in orphan_ids
        assert "REQ-011" in orphan_ids
        assert "REQ-001" not in orphan_ids
        ledger = {item["id"]: item for item in result["coverage_ledger"]}
        assert ledger["REQ-001"]["status"] == "inherited_by_target"
        assert ledger["REQ-010"]["status"] == "unassigned"
        assert ledger["REQ-011"]["status"] == "unassigned"
        assert result["coverage_complete"] is False
    finally:
        prd_path.unlink()
        arch_path.unlink()


def test_build_derive_context_matches_chinese_requirements_by_module_responsibility():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-001] 系统应支持学生上传 JPG/PNG 格式的题目图片作为答疑输入。
- [REQ-015] 系统应支持学生通过手机号和短信验证码登录。
- [REQ-016] 系统应生成 6 位数字短信验证码。
- [REQ-011] 当系统识别出题目对应知识点时，提示和完整解答应使用人教 A 版教材中的标准术语。
"""

    arch_content = """
# 02 - Module Partitioning

| Module | 包含 BC | Module 职责 |
|--------|---------|-------------|
| **Identity Module** | User Identity BC | 手机号登录、短信验证码生命周期、认证会话 |
| **Problem Intake Module** | Problem Intake BC | 隐私提示、图片上传、格式/大小/损坏校验、有效数学题识别、图片元数据 |
"""

    with tempfile.TemporaryDirectory() as arch_dir:
        prd_path = Path(arch_dir) / "parent.md"
        prd_path.write_text(prd_content, encoding="utf-8")
        arch_path = Path(arch_dir)
        (arch_path / "02-module-partitioning.md").write_text(arch_content, encoding="utf-8")

        result = build_derive_context(prd_path, arch_path, "Identity Module")
        assert result["success"] is True
        related_ids = {req["id"] for req in result["related_requirements"]}
        assert related_ids == {"REQ-015", "REQ-016"}
        assert "REQ-001" not in related_ids
        assert "REQ-011" not in related_ids


def test_build_derive_context_does_not_assign_solution_terms_to_problem_intake():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-001] 系统应支持学生上传 JPG/PNG 格式的题目图片作为答疑输入。
- [REQ-003] 系统应拒绝无法识别有效高中数学题的图片。
- [REQ-011] 当系统识别出题目对应知识点时，提示和完整解答应使用人教 A 版教材中的标准术语。
"""

    arch_content = """
# 02 - Module Partitioning

| Module | 包含 BC | Module 职责 |
|--------|---------|-------------|
| **Problem Intake Module** | Problem Intake BC | 隐私提示、图片上传、格式/大小/损坏校验、有效数学题识别、图片元数据 |
| **AI Tutoring Module** | Hint Generation BC + Solution Generation BC | 生成分层提示与完整解答，管理 LLM 调用、提示模板与缓存 |
"""

    with tempfile.TemporaryDirectory() as arch_dir:
        prd_path = Path(arch_dir) / "parent.md"
        prd_path.write_text(prd_content, encoding="utf-8")
        arch_path = Path(arch_dir)
        (arch_path / "02-module-partitioning.md").write_text(arch_content, encoding="utf-8")

        result = build_derive_context(prd_path, arch_path, "Problem Intake Module")
        assert result["success"] is True
        related_ids = {req["id"] for req in result["related_requirements"]}
        assert {"REQ-001", "REQ-003"} <= related_ids
        assert "REQ-011" not in related_ids


def test_explicit_child_allocations_override_semantic_overlap_and_support_refs(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """---
doc_id: "PROFILE-v1.0"
---

# Requirements

### Must Have
- [REQ-D001] AmazonDomainTaxonomy maps products and validates source and target domains.
- [REQ-D002] The system synthesizes and publishes a seven-dimension profile.
- [REQ-D003] The system reconciles authorized history before qualification.
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-architecture-decomposition.md").write_text(
        """# Architecture decomposition
| child_id | 责任与拥有状态 | 排除 | 分配需求 | 依赖 | 存在理由 |
|---|---|---|---|---|---|
| `EVIDENCE-QUALIFICATION` | Owns taxonomy mapping and qualification results | profile publication | D001 | HISTORY | qualification boundary |
| `PROFILE-SYNTHESIS` | Owns profile synthesis and publication from qualified inputs | taxonomy mapping | D002 | EVIDENCE | publication boundary |
| `HISTORY` | Owns authorized history reconciliation | taxonomy mapping | D003；支持 D001 | EVIDENCE | history boundary |
""",
        encoding="utf-8",
    )

    synthesis = build_derive_context(parent_prd, architecture, "PROFILE-SYNTHESIS", "component")
    evidence = build_derive_context(parent_prd, architecture, "EVIDENCE-QUALIFICATION", "component")
    history = build_derive_context(parent_prd, architecture, "HISTORY", "component")

    assert {req["id"] for req in synthesis["related_requirements"]} == {"REQ-D002"}
    assert {req["id"] for req in evidence["related_requirements"]} == {"REQ-D001"}
    assert {req["id"] for req in history["related_requirements"]} == {"REQ-D003"}
    assert synthesis["requirement_owners"]["REQ-D001"] == ["EVIDENCE-QUALIFICATION"]


