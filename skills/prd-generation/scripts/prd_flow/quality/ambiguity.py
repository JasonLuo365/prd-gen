"""Three-layer ambiguity scanner for PRD documents."""

# Ambiguous words that may refer to different concepts in different contexts
_LEXICALLY_AMBIGUOUS = {
    "用户": ["终端用户", "管理员", "系统用户", "访客"],
    "系统": ["整体系统", "子系统", "模块", "服务"],
    "数据": ["用户数据", "配置数据", "日志数据", "缓存数据"],
    "处理": ["业务处理", "数据处理", "异常处理"],
}

# Categories that should ideally be present in a complete PRD
_REQUIRED_CATEGORIES = ["安全", "认证", "授权", "错误处理", "性能", "日志"]


def scan_ambiguity(prd_text: str, requirements: list[dict] | None = None) -> dict:
    """Scan PRD for three types of ambiguity.

    Returns:
        dict with keys: lexical, logic, completeness
    """
    requirements = requirements or []

    return {
        "lexical": _scan_lexical_ambiguity(prd_text, requirements),
        "logic": _scan_logic_inconsistency(requirements),
        "completeness": _scan_completeness_gaps(prd_text, requirements),
    }


def _scan_lexical_ambiguity(text: str, requirements: list[dict]) -> list[dict]:
    """Detect ambiguous terms that may have multiple meanings."""
    findings = []
    all_text = text + " ".join(r.get("text", "") for r in requirements)

    for word, alternatives in _LEXICALLY_AMBIGUOUS.items():
        count = all_text.count(word)
        if count >= 3:  # Flag if used frequently without disambiguation
            findings.append({
                "word": word,
                "count": count,
                "possible_meanings": alternatives,
                "suggestion": f"建议明确'{word}'具体指代（如：{alternatives[0]}）",
            })

    return findings


def _scan_logic_inconsistency(requirements: list[dict]) -> list[dict]:
    """Detect contradictions between requirements."""
    findings = []

    # Check for latency vs thoroughness tension
    has_latency_req = any(_is_latency_requirement(r.get("text", "")) for r in requirements)
    has_thoroughness_req = any(_is_unbounded_thoroughness_requirement(r.get("text", "")) for r in requirements)

    if has_latency_req and has_thoroughness_req:
        findings.append({
            "type": "latency_vs_thoroughness",
            "description": "存在低延迟要求与完整处理要求的潜在矛盾",
            "suggestion": "请确认一致性校验的实现方式是否满足延迟约束",
        })

    return findings


def _is_latency_requirement(text: str) -> bool:
    has_threshold = "≤" in text or "<=" in text
    return has_threshold and ("ms" in text or "秒" in text)


def _is_unbounded_thoroughness_requirement(text: str) -> bool:
    if "完整解答" in text:
        return False
    if "全量" in text:
        return True
    return "完整" in text and any(marker in text for marker in ("处理", "校验", "扫描", "计算", "同步", "检查"))


def _scan_completeness_gaps(text: str, requirements: list[dict]) -> list[str]:
    """Detect missing requirement categories."""
    all_text = text + " ".join(r.get("text", "") for r in requirements)
    gaps = []

    for category in _REQUIRED_CATEGORIES:
        if category not in all_text:
            gaps.append(f"未检测到{category}相关需求")

    return gaps
