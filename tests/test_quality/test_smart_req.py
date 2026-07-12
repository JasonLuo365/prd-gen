from prd_flow.quality.smart_req import check_smart_req, SMARTResult


def test_specific_passes_with_concrete_nouns():
    req = {"id": "REQ-001", "text": "认证接口 P99 延迟 ≤ 200ms", "priority": "Must Have"}
    result = check_smart_req(req)
    assert result.specific is True


def test_specific_fails_with_vague_quantifiers():
    req = {"id": "REQ-002", "text": "系统应该很快", "priority": "Must Have"}
    result = check_smart_req(req)
    assert result.specific is False
    assert "模糊" in result.issues[0]


def test_measurable_passes_with_numeric_metric():
    req = {"id": "REQ-003", "text": "3 秒内完成首次内容绘制", "priority": "Must Have"}
    result = check_smart_req(req)
    assert result.measurable is True


def test_measurable_passes_with_observable_outcome_without_numeric_metric():
    req = {"id": "REQ-003A", "text": "系统应拒绝无效手机号并返回错误提示", "priority": "Must Have"}
    result = check_smart_req(req)
    assert result.measurable is True


def test_measurable_passes_with_explain_and_use_outcomes():
    for text in (
        "系统应在完整解答中按步骤说明关键推导过程",
        "提示和完整解答应使用人教 A 版教材中的标准术语",
    ):
        result = check_smart_req({"id": "REQ-003B", "text": text, "priority": "Must Have"})
        assert result.measurable is True


def test_measurable_passes_with_image_and_round_counts():
    for text in ("最多包含 3 张图片", "最多进行 5 轮成功展示的分层提示"):
        req = {"id": "REQ-003", "text": text, "priority": "Must Have"}
        result = check_smart_req(req)
        assert result.measurable is True


def test_testable_passes_with_gherkin():
    req = {
        "id": "REQ-004",
        "text": "用户可通过邮箱注册",
        "priority": "Must Have",
        "gherkin_count": 1,
    }
    result = check_smart_req(req)
    assert result.testable is True


def test_testable_fails_without_gherkin():
    req = {
        "id": "REQ-005",
        "text": "系统应具有一致性",
        "priority": "Must Have",
        "gherkin_count": 0,
    }
    result = check_smart_req(req)
    assert result.testable is False


def test_overall_pass_requires_all_dimensions():
    req = {
        "id": "REQ-006",
        "text": "认证接口 P99 延迟 ≤ 200ms",
        "priority": "Must Have",
        "gherkin_count": 1,
    }
    result = check_smart_req(req)
    assert result.overall_pass is True
