from prd_flow.output.assembler import assemble_prd


def test_assemble_root_prd():
    draft = {
        "P1": {
            "doc_id": "TEST-v1.0",
            "version": "1.0.0",
            "layer": "root",
            "author": "test",
            "created_at": "2026-05-18T10:00:00",
        },
        "P2": {
            "target_users": "电商消费者",
            "pain_points": "结账流程繁琐",
            "opportunity": "简化支付",
        },
        "P3": {
            "functional": [
                {"id": "REQ-001", "text": "支持邮箱注册", "priority": "Must Have"}
            ],
            "non_functional": [
                {"id": "NFR-001", "text": "P99 延迟 ≤ 200ms"}
            ],
        },
        "P4": {
            "scenarios": [
                {
                    "feature": "用户注册",
                    "scenario": "通过邮箱成功注册",
                    "given": "用户未登录",
                    "when": "用户提交注册表单",
                    "then": "账户创建成功",
                }
            ]
        },
        "P5": {
            "metrics": [
                {"name": "注册转化率", "target": "≥ 70%", "method": "埋点"}
            ]
        },
    }

    result = assemble_prd(draft)

    assert result.startswith("---")
    assert "doc_id: TEST-v1.0" in result
    assert "# Problem Statement" in result
    assert "# Requirements" in result
    assert "```gherkin" in result
    assert "# Success Metrics" in result
