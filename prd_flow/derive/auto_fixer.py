"""Automatic quality fixers for Derive mode requirements."""

__all__ = [
    "fix_vague_quantifiers",
    "fix_measurable",
    "fix_parent_req",
    "generate_interface_scenarios",
]

# Derive mode may clarify vague wording, but must not invent metrics or
# thresholds that are absent from the parent PRD / architecture package.
_VAGUE_REPLACEMENTS = {
    "友好": "显示错误提示信息并附重试按钮",
    "快速": "按父 PRD 或架构包已定义的时限",
    "很快": "按父 PRD 或架构包已定义的时限",
    "大量": "按父 PRD 或架构包已定义的容量范围",
    "高效": "按父 PRD 或架构包已定义的资源使用约束",
    "足够": "满足父 PRD 或架构包已定义的业务容量",
    "适当": "符合父 PRD 或架构包已定义的策略",
    "合理": "符合父 PRD 或架构包已定义的判定策略",
}


def fix_vague_quantifiers(req: dict) -> dict:
    """Replace vague words without adding unauthorized numeric commitments."""
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
    """Preserve measurable criteria without inventing thresholds.

    Derive mode can only carry metrics that are already present in the parent
    PRD or architecture package. Missing metrics are a quality/authority gap,
    not something this fixer may fill with defaults.
    """
    return req


def _word_overlap(text_a: str, text_b: str) -> float:
    """Compute word overlap similarity between two texts."""
    words_a = set(text_a.split())
    words_b = set(text_b.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def fix_parent_req(req: dict, parent_requirements: list[dict]) -> dict:
    """Link a requirement to its best-matching parent requirement by word overlap."""
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
    """Generate Gherkin scenarios only from complete interface contracts."""
    scenarios = []

    for iface in interfaces:
        if not isinstance(iface, dict):
            continue

        name = iface.get("name")
        method = iface.get("method")
        path = iface.get("path")
        request_fields = iface.get("request_fields") or []
        response_fields = iface.get("response_fields") or []
        error_codes = iface.get("error_codes") or []
        if not name or not method or not request_fields or not response_fields:
            continue

        operation = f"{method} {path}" if path else str(method)
        request_summary = ", ".join(request_fields)
        response_summary = ", ".join(response_fields)

        scenarios.append(
            {
                "feature": module_name,
                "scenario": f"{name} 正常调用",
                "given": f"模块 {module_name} 正常运行，接口契约 {name} 已按架构包定义",
                "when": f"调用 {operation} 且参数包含 {request_summary}",
                "then": f"响应体包含 {response_summary} 并符合 {name} 接口契约",
            }
        )
        if error_codes:
            error_summary = ", ".join(error_codes)
            scenarios.append(
                {
                    "feature": module_name,
                    "scenario": f"{name} 参数非法",
                    "given": f"模块 {module_name} 正常运行",
                    "when": f"调用 {operation} 且缺失或错误提供 {request_summary}",
                    "then": f"返回架构包已定义的错误码 {error_summary}",
                }
            )

    return scenarios
