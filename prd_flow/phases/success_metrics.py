"""Success metrics phase for PRD generation."""
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState


class SuccessMetricsPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P5"

    @property
    def phase_name(self) -> str:
        return "Success Metrics"

    def run(self) -> dict[str, Any]:
        """Interactive entry point."""
        print("\n[Phase 5/5] Success Metrics - 成功指标\n")

        metrics = []
        while True:
            print("添加成功指标（输入 done 结束）")
            name = input("指标名称：").strip()
            if name.lower() == "done":
                break
            target = input("目标值：").strip()
            method = input("测量方式：").strip()
            metrics.append({
                "name": name,
                "target": target,
                "method": method,
            })
            print(f"已添加 {len(metrics)} 个指标。\n")

        return self.collect(metrics=metrics)

    def collect(
        self,
        metrics: list[dict],
    ) -> dict:
        """Collect success metrics data programmatically."""
        data = {"metrics": metrics}
        self.update_state(data)
        return data
