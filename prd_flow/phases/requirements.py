"""Requirements phase for PRD generation."""
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState


class RequirementsPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P3"

    @property
    def phase_name(self) -> str:
        return "Requirements"

    def run(self) -> dict[str, Any]:
        """Interactive entry point."""
        print("\n[Phase 3/5] Requirements - 需求规格\n")

        functional = []
        while True:
            print("添加功能需求（输入 done 结束）")
            req_id = input("需求ID：").strip()
            if req_id.lower() == "done":
                break
            text = input("需求描述：").strip()
            priority = input("优先级（Must Have/Should Have/Could Have）：").strip() or "Must Have"
            gherkin_input = input("Gherkin场景数：").strip()
            gherkin_count = int(gherkin_input) if gherkin_input.isdigit() else 0
            functional.append({
                "id": req_id,
                "text": text,
                "priority": priority,
                "gherkin_count": gherkin_count,
            })
            print(f"已添加 {len(functional)} 条需求。\n")

        non_functional = []
        while True:
            print("添加非功能需求（输入 done 结束）")
            nfr_id = input("需求ID：").strip()
            if nfr_id.lower() == "done":
                break
            text = input("需求描述：").strip()
            non_functional.append({"id": nfr_id, "text": text})
            print(f"已添加 {len(non_functional)} 条非功能需求。\n")

        return self.collect(functional=functional, non_functional=non_functional)

    def collect(
        self,
        functional: list[dict],
        non_functional: list[dict],
    ) -> dict:
        """Collect requirements data programmatically."""
        data = {
            "functional": functional,
            "non_functional": non_functional,
        }
        self.update_state(data)
        return data
