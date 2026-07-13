"""SMART-REQ checker independent of test-case/Gherkin generation."""
from dataclasses import dataclass, field
import re

_VAGUE_WORDS = ["很快", "良好", "友好", "高效", "快速", "足够", "适当", "合理"]
_MEASURABLE_PATTERNS = [r"\d+\s*(ms|s|秒|分钟|小时|天)", r"\d+\s*%", r"[≤≥<>]=?\s*\d+", r"\d+\s*(个|条|次|位|张|轮|MB|GB|TB)"]
_OBSERVABLE_OUTCOME_WORDS = ["支持", "提供", "生成", "拒绝", "返回", "展示", "显示", "记录", "完成", "处理", "创建", "校验", "验证", "限制", "禁止", "允许", "上传", "登录", "选择", "点击", "包含", "不得", "仅在", "shall", "must", "reject", "return", "display"]


@dataclass
class SMARTResult:
    req_id: str
    specific: bool = False
    measurable: bool = False
    achievable: bool = True
    relevant: bool = True
    testable: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return all([self.specific, self.measurable, self.achievable, self.relevant, self.testable])


def check_smart_req(req: dict, acceptance_contracts: list[dict] | None = None) -> SMARTResult:
    text = req.get("text", "")
    result = SMARTResult(req_id=req.get("id", "UNKNOWN"))
    result.specific = not any(word in text for word in _VAGUE_WORDS)
    if not result.specific:
        result.issues.append("包含模糊量词")
    result.measurable = any(re.search(pattern, text) for pattern in _MEASURABLE_PATTERNS) or any(word in text for word in _OBSERVABLE_OUTCOME_WORDS)
    if not result.measurable:
        result.issues.append("缺少可验证指标或可观察结果")
    if req.get("release_scope", "current") != "current" or acceptance_contracts is None:
        result.testable = True
    else:
        from prd_flow.quality.oracle import validate_acceptance_contract
        result.testable = any(req.get("id") in (c.get("verifies", []) if isinstance(c.get("verifies", []), list) else [c.get("verifies")]) and not validate_acceptance_contract(c) for c in acceptance_contracts)
        if not result.testable:
            result.issues.append("缺少完整、显式的 Acceptance Contract")
    return result
