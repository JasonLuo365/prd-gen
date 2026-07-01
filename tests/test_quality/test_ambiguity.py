from prd_flow.quality.ambiguity import scan_ambiguity


def test_detects_lexical_ambiguity():
    prd_text = "用户可以通过邮箱注册。管理员可以审核用户。用户需要完成实名认证。"
    result = scan_ambiguity(prd_text)

    lexical = result["lexical"]
    assert len(lexical) > 0
    assert any("用户" in item["word"] for item in lexical)


def test_detects_logic_inconsistency():
    reqs = [
        {"id": "REQ-001", "text": "所有 API 响应时间 ≤ 50ms"},
        {"id": "REQ-002", "text": "每请求执行完整数据库一致性校验"},
    ]
    result = scan_ambiguity("", requirements=reqs)

    logic = result["logic"]
    assert len(logic) > 0


def test_allows_measured_complete_answer_generation_latency():
    reqs = [
        {"id": "NFR-003", "text": "完整解答生成响应 P95 ≤ 20 秒，测量从学生点击查看完整解答到完整解答展示。"},
        {"id": "REQ-010", "text": "系统应在完整解答中按步骤说明关键推导过程。"},
    ]
    result = scan_ambiguity("", requirements=reqs)

    assert result["logic"] == []


def test_detects_completeness_gap():
    reqs = [
        {"id": "REQ-001", "text": "用户可注册登录"},
        {"id": "REQ-002", "text": "用户可下单购买"},
    ]
    result = scan_ambiguity("", requirements=reqs)

    completeness = result["completeness"]
    # Should flag missing security requirements
    assert any("安全" in gap or "认证" in gap for gap in completeness)
