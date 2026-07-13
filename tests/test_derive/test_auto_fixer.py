"""Tests for prd_flow.derive.auto_fixer."""

from prd_flow.derive.auto_fixer import (
    fix_vague_quantifiers,
    fix_measurable,
    fix_parent_req,
)


class TestFixVagueQuantifiers:
    """Vague business language is never repaired by invention."""

    def test_vague_text_is_preserved_for_quality_gate(self):
        req = {"id": "REQ-001", "text": "系统应快速且友好地处理大量请求"}
        result = fix_vague_quantifiers(req)
        assert result is req
        assert result["text"] == req["text"]

class TestFixMeasurable:
    """Tests for fix_measurable function."""

    def test_no_keyword_does_not_invent_200ms_latency(self):
        req = {"id": "REQ-NO-METRIC", "text": "system shall record audit events"}
        result = fix_measurable(req)
        assert result is req
        assert "200ms" not in result["text"]

    def test_high_availability_does_not_invent_metric(self):
        req = {"id": "REQ-012", "text": "系统应具备高可用性"}
        result = fix_measurable(req)
        assert result is req
        assert "99.9%" not in result["text"]

    def test_availability_does_not_invent_metric(self):
        req = {"id": "REQ-013", "text": "系统应保证可用性"}
        result = fix_measurable(req)
        assert result is req
        assert "99.9%" not in result["text"]

    def test_performance_does_not_invent_latency(self):
        req = {"id": "REQ-014", "text": "系统应具备良好性能"}
        result = fix_measurable(req)
        assert result is req
        assert "200ms" not in result["text"]

    def test_latency_does_not_invent_threshold(self):
        req = {"id": "REQ-015", "text": "系统应降低延迟"}
        result = fix_measurable(req)
        assert result is req
        assert "200ms" not in result["text"]

    def test_concurrency_does_not_invent_capacity(self):
        req = {"id": "REQ-016", "text": "系统应支持高并发"}
        result = fix_measurable(req)
        assert result is req
        assert "10000" not in result["text"]

    def test_capacity_does_not_invent_storage(self):
        req = {"id": "REQ-017", "text": "系统应满足容量需求"}
        result = fix_measurable(req)
        assert result is req
        assert "1TB" not in result["text"]

    def test_already_measurable_unchanged(self):
        req = {"id": "REQ-018", "text": "系统可用性应达到 99.95%"}
        result = fix_measurable(req)
        assert result is req

    def test_already_measurable_with_number(self):
        req = {"id": "REQ-019", "text": "接口 P99 延迟 ≤ 200ms"}
        result = fix_measurable(req)
        assert result is req

    def test_already_measurable_with_percentage(self):
        req = {"id": "REQ-020", "text": "CPU 利用率应 ≥ 80%"}
        result = fix_measurable(req)
        assert result is req

    def test_no_keyword_appends_default(self):
        req = {"id": "REQ-021", "text": "系统应支持日志记录"}
        result = fix_measurable(req)
        assert result is req
        assert "200ms" not in result["text"]

    def test_returns_original_dict_when_metric_missing(self):
        req = {"id": "REQ-022", "text": "系统应具备高可用性"}
        result = fix_measurable(req)
        assert result is req
        assert result["id"] == "REQ-022"

    def test_empty_text_gets_default(self):
        req = {"id": "REQ-022b", "text": ""}
        result = fix_measurable(req)
        assert result is req

    def test_missing_text_key_gets_default(self):
        req = {"id": "REQ-022c"}
        result = fix_measurable(req)
        assert result is req

    def test_preserves_other_keys(self):
        req = {"id": "REQ-022d", "text": "系统应具备高可用性", "extra": "value"}
        result = fix_measurable(req)
        assert result["extra"] == "value"


class TestFixParentReq:
    """Tests for fix_parent_req function."""

    def test_match_adds_parent_req(self):
        req = {"id": "REQ-023", "text": "payment_gateway 应 提供 支付 接口 封装"}
        parent_requirements = [
            {"id": "REQ-005", "text": "系统 应 支持 多种 支付 方式"},
            {"id": "REQ-006", "text": "系统 应 支持 用户 管理"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert result["parent_req"] == "REQ-005"

    def test_no_match_no_parent_req(self):
        req = {"id": "REQ-024", "text": "OAuth2 登录 认证 流程"}
        parent_requirements = [
            {"id": "REQ-005", "text": "系统 应 支持 多种 支付 方式"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert "parent_req" not in result
        assert result is req

    def test_already_has_parent_req_unchanged(self):
        req = {"id": "REQ-025", "text": "payment_gateway 应 提供 支付 接口 封装", "parent_req": "REQ-001"}
        parent_requirements = [
            {"id": "REQ-005", "text": "系统 应 支持 多种 支付 方式"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert result is req
        assert result["parent_req"] == "REQ-001"

    def test_returns_new_dict_when_modified(self):
        req = {"id": "REQ-026", "text": "payment_gateway 应 提供 支付 接口 封装"}
        parent_requirements = [
            {"id": "REQ-005", "text": "系统 应 支持 多种 支付 方式"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert result is not req
        assert result["id"] == "REQ-026"

    def test_empty_parents_no_match(self):
        req = {"id": "REQ-027", "text": "系统 应 支持 OAuth2 登录"}
        result = fix_parent_req(req, [])
        assert "parent_req" not in result
        assert result is req

    def test_parent_without_text_skipped(self):
        req = {"id": "REQ-027b", "text": "payment_gateway 应 提供 支付 接口 封装"}
        parent_requirements = [
            {"id": "REQ-005"},
            {"id": "REQ-006", "text": "系统 应 支持 多种 支付 方式"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert result["parent_req"] == "REQ-006"

    def test_parent_without_id_skipped(self):
        req = {"id": "REQ-027c", "text": "payment_gateway 应 提供 支付 接口 封装"}
        parent_requirements = [
            {"text": "系统 应 支持 多种 支付 方式"},
        ]
        result = fix_parent_req(req, parent_requirements)
        assert "parent_req" not in result
