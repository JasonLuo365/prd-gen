"""Automatic quality fixers for Derive mode requirements."""

import re

__all__ = [
    "fix_vague_quantifiers",
    "fix_measurable",
    "fix_parent_req",
    "generate_interface_scenarios",
]

# Mapping of vague words/phrases to concrete replacements.
_VAGUE_REPLACEMENTS = {
    "友好": "显示错误提示信息并附重试按钮",
    "快速": "在指定时间阈值内（例如 ≤ 200ms）",
    "很快": "在指定时间阈值内（例如 ≤ 200ms）",
    "大量": "满足设计容量（例如 ≥ 10000 并发）",
    "高效": "资源利用率 ≥ 80%",
    "足够": "满足业务峰值 × 2 的容量",
    "适当": "符合行业标准的",
    "合理": "符合预设策略的",
}

# Keywords for measurable criteria injection.
_MEASURABLE_KEYWORDS = {
    "高可用": "（可用性 ≥ 99.9%）",
    "可用性": "（可用性 ≥ 99.9%）",
    "性能": "（关键接口 P99 延迟 ≤ 200ms）",
    "延迟": "（关键接口 P99 延迟 ≤ 200ms）",
    "并发": "（支持 ≥ 10000 并发用户）",
    "容量": "（存储容量 ≥ 1TB）",
}

# Pattern to detect existing measurable criteria (numbers, percentages, comparisons).
_MEASURABLE_PATTERN = re.compile(r"[0-9]|%|≥|≤|>|<|>=|<=")


def fix_vague_quantifiers(req: dict) -> dict:
    """Replace vague words in req['text'] with concrete replacements.

    Returns a new dict if any replacements were made, otherwise the original dict.
    """
    text = req.get("text", "")
    new_text = text
    changed = False

    for vague, replacement in _VAGUE_REPLACEMENTS.items():
        if vague in new_text:
            new_text = new_text.replace(vague, replacement)
            changed = True

    if not changed:
        return req

    return {**req, "text": new_text}


def fix_measurable(req: dict) -> dict:
    """Inject default measurable criteria if req['text'] lacks quantifiable metrics.

    Returns a new dict if modified, otherwise the original dict.
    """
    text = req.get("text", "")

    if _MEASURABLE_PATTERN.search(text):
        return req

    suffix = None
    for keyword, metric in _MEASURABLE_KEYWORDS.items():
        if keyword in text:
            suffix = metric
            break

    if suffix is None:
        suffix = "（需补充具体量化指标）"

    return {**req, "text": text + suffix}


def _word_overlap(text_a: str, text_b: str) -> float:
    """Compute word overlap similarity between two texts.

    Returns the Jaccard-like overlap score: |A ∩ B| / min(|A|, |B|).
    """
    words_a = set(text_a.split())
    words_b = set(text_b.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def fix_parent_req(req: dict, parent_requirements: list[dict]) -> dict:
    """Link a requirement to its best-matching parent requirement by word overlap.

    If the req already has a 'parent_req' key, returns the original dict unchanged.
    If the best overlap score is >= 0.3, adds 'parent_req': parent_id.
    Otherwise returns the original dict unchanged.
    """
    if "parent_req" in req:
        return req

    text = req.get("text", "")
    best_score = 0.0
    best_parent_id = None

    for parent in parent_requirements:
        parent_text = parent.get("text", "")
        score = _word_overlap(text, parent_text)
        if score > best_score:
            best_score = score
            best_parent_id = parent.get("id")

    if best_score >= 0.3 and best_parent_id is not None:
        return {**req, "parent_req": best_parent_id}

    return req


def generate_interface_scenarios(module_name: str, interfaces: list[dict]) -> list[dict]:
    """Generate happy-path and error-path Gherkin scenarios for each interface.

    Non-dict items in the interfaces list are skipped.
    Missing name defaults to "unknown".
    """
    scenarios = []

    for iface in interfaces:
        if not isinstance(iface, dict):
            continue

        name = iface.get("name") or "unknown"

        happy = {
            "feature": module_name,
            "scenario": f"{name} 正常调用",
            "then": "返回状态 200 且响应体符合接口契约",
        }
        error = {
            "feature": module_name,
            "scenario": f"{name} 参数非法",
            "then": "返回状态 400 且 error_code 说明错误原因",
        }

        scenarios.append(happy)
        scenarios.append(error)

    return scenarios
