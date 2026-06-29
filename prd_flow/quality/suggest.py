"""Generate fix suggestions for SMART-REQ failures."""
from prd_flow.quality.smart_req import SMARTResult


# Vague words list (mirrored from smart_req.py for suggestion generation)
_VAGUE_WORDS = ["很快", "良好", "友好", "高效", "快速", "足够", "适当", "合理"]


def suggest_fix(req: dict, smart_result: SMARTResult) -> str:
    """根据 SMART-REQ 失败项生成修正建议。"""
    suggestions = []

    if not smart_result.specific:
        text = req.get("text", "")
        found = [vw for vw in _VAGUE_WORDS if vw in text]
        if found:
            suggestions.append(f"建议替换模糊量词({', '.join(found)})为具体指标")
        else:
            suggestions.append("建议避免使用模糊描述，使用精确的术语")

    if not smart_result.measurable:
        suggestions.append("建议补充数值指标，例如'≤ 200ms'、'≥ 99.9%'或'支持1000用户'")

    if not smart_result.testable:
        suggestions.append("建议补充至少1个Gherkin场景，格式：Given...When...Then...")

    return "；".join(suggestions) if suggestions else "需求符合规范，无需修改"
