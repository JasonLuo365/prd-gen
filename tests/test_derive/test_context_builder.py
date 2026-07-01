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
