"""Success metrics collection with traceability."""
import re
from typing import Any

from prd_flow.phases.base import Phase


class SuccessMetricsPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P5"

    @property
    def phase_name(self) -> str:
        return "Success Metrics"

    def run(self) -> dict[str, Any]:
        metrics: list[dict] = []
        while True:
            name = input("指标名称（done 结束）：").strip()
            if name.lower() == "done":
                break
            metrics.append({
                "id": f"METRIC-{len(metrics) + 1:03d}",
                "name": name,
                "target": input("目标值：").strip(),
                "method": input("测量方式：").strip(),
                "verifies": [x.strip() for x in input("关联 NFR ID（逗号分隔）：").split(",") if x.strip()],
            })
        return self.collect(metrics)

    def collect(self, metrics: list[dict]) -> dict:
        for index, metric in enumerate(metrics, start=1):
            metric.setdefault("id", f"METRIC-{index:03d}")
            metric.setdefault("verifies", [])
        data = {"metrics": metrics}
        self.update_state(data)
        return data

    _MEASURABLE_RE = re.compile(r"\d+|≤|≥|<|>|%")

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        metrics = data.get("metrics", [])
        if not metrics:
            return False, "至少需要 1 个成功指标"
        for metric in metrics:
            if not metric.get("id"):
                return False, "每个成功指标必须有稳定 ID"
            if not self._MEASURABLE_RE.search(metric.get("target", "")):
                return False, f"指标 '{metric.get('name', '')}' 的目标值不可量化"
        return True, "成功指标可量化且可追溯"
