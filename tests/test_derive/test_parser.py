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
