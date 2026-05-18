from prd_flow.quality.reporter import format_quality_report
from prd_flow.quality.smart_req import SMARTResult


def test_format_smart_req_report():
    results = [
        SMARTResult(req_id="REQ-001", specific=True, measurable=True, testable=True),
        SMARTResult(
            req_id="REQ-002",
            specific=False,
            measurable=False,
            testable=False,
            issues=["包含模糊量词: 很快", "无可量化指标"],
        ),
    ]

    report = format_quality_report(smart_results=results)

    assert "SMART-REQ 检查报告" in report
    assert "REQ-001" in report
    assert "REQ-002" in report
    assert "包含模糊量词" in report
    assert "通过: 1 / 2" in report
    assert "未通过: 1" in report


def test_format_all_passing_report() -> None:
    results = [
        SMARTResult(req_id="REQ-001", specific=True, measurable=True, testable=True),
    ]

    report = format_quality_report(smart_results=results)

    assert "通过: 1 / 1" in report
    assert "未通过: 0" in report
    assert "精确性: 未通过" not in report
    assert "可度量: 未通过" not in report
    assert "可测试: 未通过" not in report


def test_format_empty_results() -> None:
    report = format_quality_report(smart_results=[])

    assert "通过: 0 / 0" in report
    assert "未通过: 0" in report


def test_format_with_ambiguity_result() -> None:
    results = [
        SMARTResult(req_id="REQ-001", specific=True, measurable=True, testable=True),
    ]

    ambiguity = {
        "lexical": [
            {
                "word": "用户",
                "count": 5,
                "suggestion": "建议明确'用户'具体指代（如：终端用户）",
            }
        ],
        "logic": [
            {
                "type": "latency_vs_thoroughness",
                "description": "存在低延迟要求与完整处理要求的潜在矛盾",
                "suggestion": "请确认一致性校验的实现方式是否满足延迟约束",
            }
        ],
        "completeness": ["未检测到安全相关需求"],
    }

    report = format_quality_report(smart_results=results, ambiguity_result=ambiguity)

    assert "歧义扫描" in report
    assert "词汇歧义: 发现 1 处" in report
    assert "'用户' 使用 5 次" in report
    assert "逻辑一致性: 发现 1 处潜在矛盾" in report
    assert "完整性缺口: 发现 1 处" in report
    assert "未检测到安全相关需求" in report
