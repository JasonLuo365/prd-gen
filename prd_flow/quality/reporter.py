"""Format and display quality check results."""
from prd_flow.quality.smart_req import SMARTResult


def format_quality_report(
    smart_results: list[SMARTResult],
    ambiguity_result: dict | None = None,
) -> str:
    """Format a comprehensive quality report."""
    lines = []
    lines.append("=" * 50)
    lines.append("PRD 质量审查报告")
    lines.append("=" * 50)

    # SMART-REQ section
    lines.append("\n## SMART-REQ 检查报告")
    lines.append("-" * 30)

    pass_count = sum(1 for r in smart_results if r.overall_pass)
    fail_count = len(smart_results) - pass_count

    lines.append(f"通过: {pass_count} / {len(smart_results)}")
    lines.append(f"未通过: {fail_count}\n")

    for result in smart_results:
        status = "通过" if result.overall_pass else "未通过"
        symbol = "通过" if result.overall_pass else "未通过"
        lines.append(f"[{symbol}] {result.req_id}: {status}")

        if not result.specific:
            lines.append(f"      精确性: 未通过")
        if not result.measurable:
            lines.append(f"      可度量: 未通过")
        if not result.testable:
            lines.append(f"      可测试: 未通过")

        for issue in result.issues:
            lines.append(f"      ⚠️  {issue}")

    # Ambiguity section
    if ambiguity_result:
        lines.append("\n## 歧义扫描")
        lines.append("-" * 30)

        lexical = ambiguity_result.get("lexical", [])
        if lexical:
            lines.append(f"\n词汇歧义: 发现 {len(lexical)} 处")
            for item in lexical:
                lines.append(f"  - '{item['word']}' 使用 {item['count']} 次，{item['suggestion']}")

        logic = ambiguity_result.get("logic", [])
        if logic:
            lines.append(f"\n逻辑一致性: 发现 {len(logic)} 处潜在矛盾")
            for item in logic:
                lines.append(f"  - {item['description']}")
                lines.append(f"    建议: {item['suggestion']}")

        completeness = ambiguity_result.get("completeness", [])
        if completeness:
            lines.append(f"\n完整性缺口: 发现 {len(completeness)} 处")
            for gap in completeness:
                lines.append(f"  - {gap}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
