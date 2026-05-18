"""End-to-end integration test for PRD generation workflow."""
from pathlib import Path
from prd_flow.output.assembler import assemble_prd
from prd_flow.quality.ambiguity import scan_ambiguity
from prd_flow.quality.smart_req import check_smart_req


def test_end_to_end_root_prd_generation():
    """Test complete flow: collect data → quality check → assemble."""
    # Simulate collected draft content
    draft = {
        "P1": {
            "doc_id": "ECOMMERCE-v1.0",
            "version": "1.0.0",
            "layer": "root",
            "author": "test",
            "status": "draft",
            "priority": "P0",
            "created_at": "2026-05-18T10:00:00",
            "tags": ["ecommerce"],
        },
        "P2": {
            "target_users": "电商消费者",
            "pain_points": "结账流程繁琐",
            "opportunity": "一键支付",
        },
        "P3": {
            "functional": [
                {
                    "id": "REQ-001",
                    "text": "支持邮箱注册，密码需包含8位以上字母数字组合",
                    "priority": "Must Have",
                    "gherkin_count": 2,
                },
                {
                    "id": "REQ-002",
                    "text": "系统响应时间 ≤ 200ms",
                    "priority": "Must Have",
                    "gherkin_count": 1,
                },
            ],
            "non_functional": [
                {"id": "NFR-001", "text": "可用性 ≥ 99.9%"},
            ],
        },
        "P4": {
            "scenarios": [
                {
                    "feature": "用户注册",
                    "scenario": "通过邮箱成功注册",
                    "given": "用户访问注册页面",
                    "when": "用户输入有效邮箱和密码",
                    "then": "账户创建成功",
                },
            ]
        },
        "P5": {
            "metrics": [
                {"name": "注册转化率", "target": "≥ 70%", "method": "埋点统计"},
            ]
        },
    }

    # Quality checks
    req = draft["P3"]["functional"][0]
    smart_result = check_smart_req(req)
    assert smart_result.overall_pass is True

    # Assemble
    prd = assemble_prd(draft)
    assert "ECOMMERCE-v1.0" in prd
    assert "```gherkin" in prd

    # Scan for ambiguity
    ambiguity = scan_ambiguity(prd, draft["P3"]["functional"])
    assert "lexical" in ambiguity
    assert "logic" in ambiguity
    assert "completeness" in ambiguity
