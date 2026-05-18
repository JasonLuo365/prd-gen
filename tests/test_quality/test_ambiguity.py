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


def test_detects_completeness_gap():
    reqs = [
        {"id": "REQ-001", "text": "用户可注册登录"},
        {"id": "REQ-002", "text": "用户可下单购买"},
    ]
    result = scan_ambiguity("", requirements=reqs)

    completeness = result["completeness"]
    # Should flag missing security requirements
    assert any("安全" in gap or "认证" in gap for gap in completeness)
