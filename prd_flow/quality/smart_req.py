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
    r"\d+\s*(个|条|次|MB|GB|TB)",  # counts and sizes
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

    # Measurable: Check for numeric patterns
    result.measurable = any(re.search(p, text) for p in _MEASURABLE_PATTERNS)
    if not result.measurable:
        result.issues.append("无可量化指标，建议补充具体数值")

    # Testable: Must-Have must have Gherkin coverage
    if priority == "Must Have":
        result.testable = gherkin_count >= 1
        if not result.testable:
            result.issues.append("Must-Have 需求至少需要 1 个 Gherkin 场景")
    else:
        result.testable = True  # Optional requirements can be testable but not enforced

    return result
