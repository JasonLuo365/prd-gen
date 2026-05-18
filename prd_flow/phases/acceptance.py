"""Acceptance criteria phase for PRD generation."""
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState


class AcceptancePhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P4"

    @property
    def phase_name(self) -> str:
        return "Acceptance"

    def run(self) -> dict[str, Any]:
        """Interactive entry point."""
        print("\n[Phase 4/5] Acceptance - 验收标准\n")

        scenarios = []
        while True:
            print("添加 Gherkin 场景（输入 done 结束）")
            feature = input("Feature 名称：").strip()
            if feature.lower() == "done":
                break
            scenario = input("Scenario 名称：").strip()
            given = input("Given：").strip()
            when = input("When：").strip()
            then = input("Then：").strip()
            scenarios.append({
                "feature": feature,
                "scenario": scenario,
                "given": given,
                "when": when,
                "then": then,
            })
            print(f"已添加 {len(scenarios)} 个场景。\n")

        return self.collect(scenarios=scenarios)

    def collect(
        self,
        scenarios: list[dict],
    ) -> dict:
        """Collect acceptance data programmatically."""
        data = {"scenarios": scenarios}
        self.update_state(data)
        return data
