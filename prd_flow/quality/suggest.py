"""Generate source-safe fix suggestions for SMART-REQ failures."""
from prd_flow.quality.smart_req import SMARTResult


def suggest_fix(req: dict, smart_result: SMARTResult) -> str:
    suggestions: list[str] = []
    if not smart_result.specific:
        suggestions.append("将模糊描述改为明确条件、对象和约束")
    if not smart_result.measurable:
        suggestions.append("补充来源已授权的量化指标或可观察通过/失败结果")
    if not smart_result.testable:
        suggestions.append("补充完整 Acceptance Contract；不要由 Agent 猜测业务响应")
    return "；".join(suggestions) if suggestions else "需求符合规范"
