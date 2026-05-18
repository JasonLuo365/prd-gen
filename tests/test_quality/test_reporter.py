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
