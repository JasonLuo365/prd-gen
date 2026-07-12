"""Tests for prd_flow.derive.auto_fixer."""

import pytest

from prd_flow.derive.auto_fixer import (
    fix_vague_quantifiers,
    fix_measurable,
    fix_parent_req,
    generate_interface_scenarios,
)


class TestFixVagueQuantifiers:
    """Tests for fix_vague_quantifiers function."""

    def test_replaces_friendly(self):
        req = {"id": "REQ-001", "text": "系统应友好提示用户"}
        result = fix_vague_quantifiers(req)
        assert "友好" not in result["text"]
        assert "显示错误提示信息并附重试按钮" in result["text"]

    def test_replaces_fast(self):
        req = {"id": "REQ-002", "text": "系统应快速响应"}
        result = fix_vague_quantifiers(req)
        assert "快速" not in result["text"]
        assert "按父 PRD 或架构包已定义的时限" in result["text"]
        assert "200ms" not in result["text"]

    def test_replaces_very_fast(self):
        req = {"id": "REQ-003", "text": "系统应很快处理请求"}
        result = fix_vague_quantifiers(req)
        assert "很快" not in result["text"]
        assert "按父 PRD 或架构包已定义的时限" in result["text"]
        assert "200ms" not in result["text"]

    def test_replaces_massive(self):
        req = {"id": "REQ-004", "text": "系统应支持大量并发"}
        result = fix_vague_quantifiers(req)
        assert "大量" not in result["text"]
        assert "按父 PRD 或架构包已定义的容量范围" in result["text"]
        assert "10000" not in result["text"]

    def test_replaces_efficient(self):
        req = {"id": "REQ-005", "text": "系统应高效运行"}
        result = fix_vague_quantifiers(req)
        assert "高效" not in result["text"]
        assert "按父 PRD 或架构包已定义的资源使用约束" in result["text"]
        assert "80%" not in result["text"]

    def test_replaces_enough(self):
        req = {"id": "REQ-006", "text": "系统应提供足够容量"}
        result = fix_vague_quantifiers(req)
        assert "足够" not in result["text"]
        assert "满足父 PRD 或架构包已定义的业务容量" in result["text"]

    def test_replaces_appropriate(self):
        req = {"id": "REQ-007", "text": "系统应采取适当措施"}
        result = fix_vague_quantifiers(req)
        assert "适当" not in result["text"]
        assert "符合父 PRD 或架构包已定义的策略" in result["text"]

    def test_replaces_reasonable(self):
        req = {"id": "REQ-008", "text": "系统应做出合理判断"}
        result = fix_vague_quantifiers(req)
        assert "合理" not in result["text"]
        assert "符合父 PRD 或架构包已定义的判定策略" in result["text"]

    def test_no_vague_words_unchanged(self):
        req = {"id": "REQ-009", "text": "系统应支持 OAuth2 登录"}
        result = fix_vague_quantifiers(req)
        assert result is req
        assert result["text"] == "系统应支持 OAuth2 登录"

    def test_multiple_vague_words_all_replaced(self):
        req = {"id": "REQ-010", "text": "系统应快速且友好地处理大量请求"}
        result = fix_vague_quantifiers(req)
        assert "快速" not in result["text"]
        assert "友好" not in result["text"]
        assert "大量" not in result["text"]
        assert "按父 PRD 或架构包已定义的时限" in result["text"]
        assert "显示错误提示信息并附重试按钮" in result["text"]
        assert "按父 PRD 或架构包已定义的容量范围" in result["text"]
        assert "200ms" not in result["text"]
        assert "10000" not in result["text"]

    def test_returns_new_dict(self):
        req = {"id": "REQ-011", "text": "系统应友好提示"}
        result = fix_vague_quantifiers(req)
        assert result is not req
        assert result["id"] == "REQ-011"

    def test_empty_text_unchanged(self):
        req = {"id": "REQ-011b", "text": ""}
        result = fix_vague_quantifiers(req)
        assert result is req

    def test_missing_text_key_unchanged(self):
        req = {"id": "REQ-011c"}
        result = fix_vague_quantifiers(req)
        assert result is req

    def test_preserves_other_keys(self):
        req = {"id": "REQ-011d", "text": "系统应友好提示", "extra": "value"}
        result = fix_vague_quantifiers(req)
        assert result["extra"] == "value"
        assert result["text"] != req["text"]


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


class TestGenerateInterfaceScenarios:
    """Tests for generate_interface_scenarios function."""

    def _contract(self, name="createOrder", method="POST", path="/orders", error_codes=None):
        return {
            "name": name,
            "method": method,
            "path": path,
            "request_fields": ["order_id"],
            "response_fields": ["status"],
            "error_codes": error_codes or ["400"],
        }

    def test_incomplete_acl_interface_does_not_generate_authoritative_scenarios(self):
        interfaces = [
            {"name": "SMS Gateway", "source": "06-interface-contracts.md", "method": "", "error_codes": []}
        ]
        scenarios = generate_interface_scenarios("Identity Module", interfaces)
        assert scenarios == []

    def test_contract_scenario_uses_declared_fields_and_error_code(self):
        interfaces = [
            {
                "name": "Upload Image",
                "method": "POST",
                "path": "/api/v1/problems/images",
                "request_fields": ["student_id", "images"],
                "response_fields": ["image_upload_id", "validation_status"],
                "error_codes": ["422"],
            }
        ]
        scenarios = generate_interface_scenarios("Problem Intake Module", interfaces)
        assert len(scenarios) == 2
        assert "student_id" in scenarios[0]["when"]
        assert "image_upload_id" in scenarios[0]["then"]
        assert "422" in scenarios[1]["then"]
        assert "400" not in scenarios[1]["then"]

    def test_contract_without_declared_errors_generates_only_happy_path(self):
        interface = self._contract(error_codes=[])
        interface["error_codes"] = []

        scenarios = generate_interface_scenarios("order_module", [interface])

        assert len(scenarios) == 1
        assert scenarios[0]["scenario"] == "createOrder 正常调用"

    def test_one_interface_two_scenarios(self):
        interfaces = [
            self._contract(),
        ]
        scenarios = generate_interface_scenarios("order_module", interfaces)
        assert len(scenarios) == 2

    def test_happy_path_contains_response_fields(self):
        interfaces = [
            self._contract(),
        ]
        scenarios = generate_interface_scenarios("order_module", interfaces)
        happy = scenarios[0]
        assert "status" in happy["then"]
        assert "正常调用" in happy["scenario"]

    def test_error_path_contains_declared_error_code(self):
        interfaces = [
            self._contract(error_codes=["422"]),
        ]
        scenarios = generate_interface_scenarios("order_module", interfaces)
        error = scenarios[1]
        assert "422" in error["then"]
        assert "参数非法" in error["scenario"]

    def test_skip_non_dict_items(self):
        interfaces = [
            self._contract(),
            "not a dict",
            123,
            None,
        ]
        scenarios = generate_interface_scenarios("order_module", interfaces)
        assert len(scenarios) == 2

    def test_default_values_for_missing_fields(self):
        interfaces = [
            {"method": "GET"},
        ]
        scenarios = generate_interface_scenarios("test_module", interfaces)
        assert scenarios == []

    def test_two_interfaces_four_scenarios(self):
        interfaces = [
            self._contract(),
            self._contract(name="getOrder", method="GET", path="/orders/{id}", error_codes=["404"]),
        ]
        scenarios = generate_interface_scenarios("order_module", interfaces)
        assert len(scenarios) == 4
        scenarios_names = [s["scenario"] for s in scenarios]
        assert "createOrder 正常调用" in scenarios_names
        assert "createOrder 参数非法" in scenarios_names
        assert "getOrder 正常调用" in scenarios_names
        assert "getOrder 参数非法" in scenarios_names

    def test_empty_interfaces_returns_empty(self):
        scenarios = generate_interface_scenarios("order_module", [])
        assert scenarios == []

    def test_module_name_used_as_feature(self):
        interfaces = [
            self._contract(name="foo", method="GET", path="/bar", error_codes=["404"]),
        ]
        scenarios = generate_interface_scenarios("used_module", interfaces)
        assert scenarios[0]["feature"] == "used_module"
        assert scenarios[1]["feature"] == "used_module"

    def test_interface_with_none_name_uses_unknown(self):
        interfaces = [
            {"name": None, "method": "GET", "path": "/bar", "request_fields": ["id"], "response_fields": ["body"], "error_codes": ["404"]},
        ]
        scenarios = generate_interface_scenarios("test", interfaces)
        assert scenarios == []

    def test_all_non_dict_items_skipped(self):
        interfaces = ["a", 1, None, [], set()]
        scenarios = generate_interface_scenarios("test", interfaces)
        assert scenarios == []
