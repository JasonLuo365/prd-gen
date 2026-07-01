import tempfile
from pathlib import Path

from prd_flow.derive.parser import parse_parent_prd, extract_module_context


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
