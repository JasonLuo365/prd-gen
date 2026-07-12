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


def test_build_derive_context_keeps_tutoring_session_scope_narrow():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-002] 系统应限制单次题目输入最多包含 3 张图片。
- [REQ-004] 系统应要求学生在开始答疑前选择基础水平。
- [REQ-005] 系统应基于学生选择的基础水平生成分层提示。
- [REQ-006] 每一轮分层提示应包含提示方向和一个追问问题，默认不直接给关键计算结果。
- [REQ-007] 单题最多进行 5 轮成功展示的分层提示。
- [REQ-009] 系统应从第一轮提示成功展示后展示“查看完整解答”按钮。
- [REQ-013] 系统应在上传前向学生展示隐私提示，说明图片和会话数据仅用于本次答疑、学生在保存期内查看本次答疑记录及必要的问题排查，默认 30 天后删除，且不得用于模型训练。
"""

    arch_content = """
# 02 - Module Partitioning

| Module | 包含 BC | Module 职责 |
|--------|---------|-------------|
| **Problem Intake Module** | Problem Intake BC | 隐私提示、图片上传、格式/大小/损坏校验、有效数学题识别、图片元数据 |
| **Tutoring Session Module** | Tutoring Session BC | 基础水平选择、会话生命周期、提示轮次计数、解答请求门控 |
| **AI Tutoring Module** | Hint Generation BC + Solution Generation BC | 生成分层提示与完整解答，管理 LLM 调用、提示模板与缓存 |
"""

    with tempfile.TemporaryDirectory() as arch_dir:
        prd_path = Path(arch_dir) / "parent.md"
        prd_path.write_text(prd_content, encoding="utf-8")
        arch_path = Path(arch_dir)
        (arch_path / "02-module-partitioning.md").write_text(arch_content, encoding="utf-8")

        result = build_derive_context(prd_path, arch_path, "Tutoring Session Module")
        assert result["success"] is True
        related_ids = {req["id"] for req in result["related_requirements"]}
        assert related_ids == {"REQ-004", "REQ-007", "REQ-009"}


def test_build_derive_context_keeps_ai_tutoring_content_scope_narrow():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-004] 系统应要求学生在开始答疑前选择基础水平。
- [REQ-005] 系统应基于学生选择的基础水平生成分层提示。
- [REQ-006] 每一轮分层提示应包含提示方向和一个追问问题，默认不直接给关键计算结果。
- [REQ-007] 单题最多进行 5 轮成功展示的分层提示。
- [REQ-009] 系统应从第一轮提示成功展示后展示“查看完整解答”按钮。

### Should Have
- [REQ-010] 系统应在完整解答中按步骤说明关键推导过程。
- [REQ-011] 当系统识别出题目对应知识点时，提示和完整解答应使用人教 A 版教材中的标准术语。
"""

    arch_content = """
# 02 - Module Partitioning

| Module | 包含 BC | Module 职责 |
|--------|---------|-------------|
| **Tutoring Session Module** | Tutoring Session BC | 基础水平选择、会话生命周期、提示轮次计数、解答请求门控 |
| **AI Tutoring Module** | Hint Generation BC + Solution Generation BC | 生成分层提示与完整解答，管理 LLM 调用、提示模板与缓存 |
"""

    with tempfile.TemporaryDirectory() as arch_dir:
        prd_path = Path(arch_dir) / "parent.md"
        prd_path.write_text(prd_content, encoding="utf-8")
        arch_path = Path(arch_dir)
        (arch_path / "02-module-partitioning.md").write_text(arch_content, encoding="utf-8")

        result = build_derive_context(prd_path, arch_path, "AI Tutoring Module")
        assert result["success"] is True
        related_ids = {req["id"] for req in result["related_requirements"]}
        assert related_ids == {"REQ-005", "REQ-006", "REQ-010", "REQ-011"}


def test_build_derive_context_prioritizes_retention_ownership_over_image_terms():
    prd_content = """---
doc_id: "PARENT-v1.0"
---

# Requirements

## 功能需求

### Must Have
- [REQ-013] 系统应在上传前向学生展示隐私提示，说明图片和会话数据仅用于本次答疑、默认 30 天后删除，且不得用于模型训练。
- [REQ-014] 系统应从图片上传成功时间 T 起算，在 T + 30 天内允许读取该次答疑的原始图片和会话数据；到达 T + 30 天 + 1 分钟时，原始图片和会话数据必须变为系统不可读取。

## 非功能需求
- [NFR-005] 原始图片和会话数据的默认保存时间不得超过 30 天。测量从图片上传成功时间 T 开始。
- [NFR-006] 系统不得将学生上传图片或会话数据用于模型训练。
"""

    arch_content = """
# 02 - Module Partitioning

| Module | 包含 BC | Module 职责 |
|--------|---------|-------------|
| **Problem Intake Module** | Problem Intake BC | 隐私提示、图片上传、格式/大小/损坏校验、有效数学题识别、图片元数据 |
| **Compliance & Retention Module** | Data Retention & Compliance BC | 30 天保留策略、定时删除、合规审计、训练使用禁止 |
"""

    with tempfile.TemporaryDirectory() as arch_dir:
        prd_path = Path(arch_dir) / "parent.md"
        prd_path.write_text(prd_content, encoding="utf-8")
        arch_path = Path(arch_dir)
        (arch_path / "02-module-partitioning.md").write_text(arch_content, encoding="utf-8")

        compliance = build_derive_context(prd_path, arch_path, "Compliance & Retention Module")
        assert compliance["success"] is True
        assert {req["id"] for req in compliance["related_requirements"]} == {"REQ-014"}
        assert {nfr["id"] for nfr in compliance["related_non_functional"]} == {"NFR-005", "NFR-006"}

        intake = build_derive_context(prd_path, arch_path, "Problem Intake Module")
        assert intake["success"] is True
        assert {req["id"] for req in intake["related_requirements"]} == {"REQ-013"}


def test_component_context_maps_problem_intake_requirements(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """---
doc_id: "PROBLEM-INTAKE-v1.0"
---

# Requirements

### Must Have
- [REQ-D001] Problem Intake Module 应在自身职责边界内满足父需求：系统应支持学生上传 JPG/PNG 格式的题目图片作为答疑输入。
- [REQ-D002] Problem Intake Module 应在自身职责边界内满足父需求：系统应限制单次题目输入最多包含 3 张图片；当学生已选择 3 张图片时，前端应禁止继续添加第 4 张；当后端收到超过 3 张图片的上传请求时，后端应拒绝请求并返回图片数量超限错误。
- [REQ-D003] Problem Intake Module 应在自身职责边界内满足父需求：系统应拒绝单张超过 10MB、损坏图片、非 JPG/PNG 文件，或无法识别有效高中数学题的图片，并展示明确错误提示。
- [REQ-D004] Problem Intake Module 应在自身职责边界内满足父需求：系统应在上传前向学生展示隐私提示，说明图片和会话数据仅用于本次答疑。
- [REQ-D005] Problem Intake Module 应在自身职责边界内满足父需求：系统应从图片上传成功时间 T 起算，在 T + 30 天内允许读取该次答疑的原始图片和会话数据；到达 T + 30 天 + 1 分钟时，原始图片和会话数据必须变为系统不可读取。
""",
        encoding="utf-8",
    )
    arch_output = tmp_path / "architecture" / "output"
    arch_output.mkdir(parents=True)
    (arch_output / "02-module-partitioning.md").write_text(
        """# 02 Module Partitioning

## Component Partitioning

| Component | Responsibility | Related Aggregate |
|---|---|---|
| Consent Component | 隐私提示展示、学生确认、同意记录管理 | PrivacyConsent |
| Image Submission Component | 图片集提交、数量限制、对象存储写入 | ImageSubmission, RawImage |
| Image Validation Component | 格式校验、大小校验、损坏检测 | ImageSubmission |
| Math Recognition Component | 调用外部识别服务、解析识别结果 | MathProblemRecognition |
| Session Lifecycle Component | 会话创建、状态管理、完成判定、保存期过期 | ProblemIntakeSession |
""",
        encoding="utf-8",
    )

    consent = build_derive_context(parent_prd, tmp_path / "architecture", "Consent Component", "component")
    validation = build_derive_context(parent_prd, tmp_path / "architecture", "Image Validation Component", "component")
    lifecycle = build_derive_context(parent_prd, tmp_path / "architecture", "Session Lifecycle Component", "component")

    assert [req["id"] for req in consent["related_requirements"]] == ["REQ-D004"]
    assert [req["id"] for req in validation["related_requirements"]] == ["REQ-D003"]
    assert [req["id"] for req in lifecycle["related_requirements"]] == ["REQ-D005"]


def test_recursive_derive_blocks_lost_parent_architecture_interface(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """# Requirements

### Must Have
- [REQ-D001] 系统应支持上传 JPG/PNG 图片作为答疑输入。
  - parent_req: REQ-001
  - source_kind: parent_requirement
- [REQ-A001] 模块必须提供 GET /api/v1/problems/images/{imageId}/validation 查询接口。
  - parent_req: ARCH:06-interface-contracts.md#API-PI-002
  - source_kind: architecture_interface
- [REQ-A002] 模块必须为 ProblemImage 提供数据库迁移。
  - parent_req: ARCH:05-data-model.md
  - source_kind: architecture_data
- [REQ-A003] 模块必须按父架构事件契约生成、发布或处理事件 ImageUploaded。
  - parent_req: ARCH:06-interface-contracts.md#EVT-PI-001
  - source_kind: architecture_event
- [REQ-A004] 模块必须记录并提供成功率指标证据。
  - parent_req: MET:MET-001
  - source_kind: architecture_observability
- [REQ-A005] 模块必须提供学生端前端页面并完整实现 REQ-D001 的交互。
  - parent_req: ARCH:03-runtime-architecture.md#Web App
  - related_reqs: [REQ-D001]
  - source_kind: architecture_frontend
""",
        encoding="utf-8",
    )
    arch_output = tmp_path / "architecture" / "output"
    arch_output.mkdir(parents=True)
    (arch_output / "02-module-partitioning.md").write_text(
        """| Component | Responsibility | Related Aggregate |
|---|---|---|
| Image Submission Component | 图片集提交、数量限制、对象存储写入 | ImageSubmission |
""",
        encoding="utf-8",
    )
    (arch_output / "05-data-model.md").write_text(
        """## Aggregate Roots
| Aggregate Root | Responsibility | Stored In |
|---|---|---|
| ImageSubmission | 图片提交 | PostgreSQL |
""",
        encoding="utf-8",
    )

    context = build_derive_context(
        parent_prd,
        tmp_path / "architecture",
        "Image Submission Component",
        "component",
    )

    assert [req["id"] for req in context["related_requirements"]] == ["REQ-D001"]
    assert [req["id"] for req in context["related_architecture_requirements"]] == ["REQ-A002"]
    assert context["data_parent_refs"] == ["REQ-A002"]
    assert any("REQ-A001" in gap and "not represented" in gap for gap in context["coverage_gaps"])
    assert any("REQ-A003" in gap and "no child owner" in gap for gap in context["coverage_gaps"])
    assert any("REQ-A004" in gap and "no child metric owner" in gap for gap in context["coverage_gaps"])
    assert any("REQ-A005" in gap and "no child owner" in gap for gap in context["coverage_gaps"])


def test_login_input_and_code_request_are_preserved_as_frontend_work(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """# Requirements

### Must Have
- [REQ-015] 系统应支持学生通过手机号和短信验证码登录。

# Acceptance

```gherkin
Feature: 手机号验证码登录

  @REQ-015
  Scenario: 学生使用短信验证码登录
    Given 学生在登录页输入手机号并请求短信验证码
    When 学生连续 5 次输入错误验证码并提交登录
    Then 系统创建认证会话
```
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-module-partitioning.md").write_text(
        """| Module | Included BC | Responsibility |
|---|---|---|
| **Identity Module** | User Identity BC | 手机号登录、短信验证码生命周期、认证会话 |
""",
        encoding="utf-8",
    )

    context = build_derive_context(
        parent_prd,
        architecture,
        "Identity Module",
        "deployable_module",
    )

    assert context["success"] is True
    assert context["coverage_gaps"] == []
    assert "frontend" in context["requirement_surfaces"]["REQ-015"]
    assert "frontend" in context["implementation_surfaces"]


def test_frontend_architecture_owner_inherits_linked_business_behavior(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """# Requirements

### Must Have
- [REQ-D001] 系统应拒绝超过 3 张图片的提交请求。
  - parent_req: REQ-002
  - implementation_surfaces: [frontend, api_backend, domain_logic]
  - source_kind: parent_requirement
- [REQ-A001] 模块必须提供学生端前端页面并完整实现 REQ-D001 的交互。
  - parent_req: ARCH:03-runtime-architecture.md#Web App
  - related_reqs: [REQ-D001]
  - implementation_surfaces: [frontend]
  - source_kind: architecture_frontend

# Acceptance

```gherkin
Feature: 图片数量限制

  @REQ-D001
  Scenario: 第四张图片被阻止
    Given 学生已选择 3 张图片
    When 学生添加第 4 张图片
    Then 前端不允许继续添加图片
```
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-module-partitioning.md").write_text(
        """| Component | Responsibility | Related Aggregate |
|---|---|---|
| **Student Web UI Component** | 学生端前端页面、浏览器交互与状态展示 | None |
| **Image Policy Component** | 图片提交请求数量限制 | None |
""",
        encoding="utf-8",
    )

    context = build_derive_context(
        parent_prd,
        architecture,
        "Student Web UI Component",
        "component",
    )

    assert context["coverage_gaps"] == []
    assert [req["id"] for req in context["related_requirements"]] == ["REQ-D001"]
    assert [req["id"] for req in context["related_architecture_requirements"]] == ["REQ-A001"]
    assert [scenario["scenario"] for scenario in context["related_scenarios"]] == ["第四张图片被阻止"]
    assert context["artifact_parent_refs"]["frontend"] == ["REQ-A001"]


def test_user_activity_in_given_does_not_create_false_frontend_scope(tmp_path: Path):
    parent_prd = tmp_path / "prd.md"
    parent_prd.write_text(
        """# Requirements

### Must Have
- [REQ-014] 系统应在 T + 30 天 + 1 分钟使原始图片和会话数据不可读取。

# Acceptance

```gherkin
Feature: 数据删除

  @REQ-014
  Scenario: 保存期结束后数据不可读取
    Given 学生已上传题目图片并完成一次答疑
    When 当前时间到达 T + 30 天 + 1 分钟
    Then 原始图片和会话数据不可读取
```
""",
        encoding="utf-8",
    )
    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "02-module-partitioning.md").write_text(
        """| Module | Included BC | Responsibility |
|---|---|---|
| **Compliance Module** | Compliance BC | 30 天保留策略、定时删除与审计 |
""",
        encoding="utf-8",
    )

    context = build_derive_context(
        parent_prd,
        architecture,
        "Compliance Module",
        "deployable_module",
    )

    assert "frontend" not in context["requirement_surfaces"]["REQ-014"]
    assert "frontend" not in context["implementation_surfaces"]
