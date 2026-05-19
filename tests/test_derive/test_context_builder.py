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
