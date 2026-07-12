"""SMART-REQ quality checker for PRD requirements."""
from dataclasses import dataclass, field
import re


# Vague quantifiers that fail Specific check
_VAGUE_WORDS = ["很快", "良好", "友好", "高效", "快速", "足够", "适当", "合理"]

# Patterns that indicate measurable criteria
_MEASURABLE_PATTERNS = [
    r"\d+\s*(ms|s|秒|分钟|小时|天)",  # time
    r"\d+\s*%",  # percentage
    r"[≥≤<>]=?\s*\d+",  # comparisons with numbers
    r"\d+\s*(个|条|次|位|张|轮|MB|GB|TB)",  # counts and sizes
]

_OBSERVABLE_OUTCOME_WORDS = [
    "支持",
    "提供",
    "实现",
    "生成",
    "拒绝",
    "返回",
    "展示",
    "显示",
    "记录",
    "说明",
    "使用",
    "完成",
    "处理",
    "执行",
    "创建",
    "校验",
    "验证",
    "限制",
    "禁止",
    "允许",
    "失效",
    "上传",
    "登录",
    "选择",
    "点击",
    "包含",
    "不得",
    "不再",
    "仅在",
    "should",
    "shall",
    "must",
    "execute",
    "complete",
    "process",
    "reject",
    "return",
    "display",
    "create",
    "record",
    "validate",
]


@dataclass
class SMARTResult:
    """Result of SMART-REQ checking for a single requirement."""

    req_id: str
    specific: bool = False
    measurable: bool = False
    achievable: bool = True  # Default to True; hard to check automatically
    relevant: bool = True  # Default to True; checked at Derive mode level
    testable: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        """All mandatory dimensions pass."""
        return all([self.specific, self.measurable, self.achievable, self.relevant, self.testable])


def check_smart_req(req: dict) -> SMARTResult:
    """Check a single requirement against SMART-REQ criteria."""
    text = req.get("text", "")
    req_id = req.get("id", "UNKNOWN")
    priority = req.get("priority", "")
    gherkin_count = req.get("gherkin_count", 0)

    result = SMARTResult(req_id=req_id)

    # Specific: Check for vague quantifiers
    result.specific = not any(vw in text for vw in _VAGUE_WORDS)
    if not result.specific:
        found = [vw for vw in _VAGUE_WORDS if vw in text]
        result.issues.append(f"包含模糊量词: {', '.join(found)}")

    # Measurable: numeric metric or observable pass/fail behavior.
    result.measurable = any(re.search(p, text) for p in _MEASURABLE_PATTERNS) or any(
        word in text for word in _OBSERVABLE_OUTCOME_WORDS
    )
    if not result.measurable:
        result.issues.append("缺少可验证指标或可观察结果")

    # Testable: Must-Have must have Gherkin coverage
    if priority == "Must Have":
        result.testable = gherkin_count >= 1
        if not result.testable:
            result.issues.append("Must-Have 需求至少需要 1 个 Gherkin 场景")
    else:
        result.testable = True  # Optional requirements can be testable but not enforced

    return result
