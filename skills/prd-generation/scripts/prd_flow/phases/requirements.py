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

        # Step 1: Diverge Collection
        print("Step 1/4: 发散收集 — 请描述系统应具备的核心功能（每行一个，输入 done 结束）：")
        features = []
        while True:
            line = input("> ").strip()
            if line.lower() == "done":
                break
            if line:
                features.append(line)

        # Step 2: Classify
        print("\nStep 2/4: 分类标注\n")
        classified = []
        for idx, feature in enumerate(features, start=1):
            req_id = f"REQ-{idx:03d}"
            priority = input(f'"{feature}" 的优先级（Must Have/Should Have/Could Have）：').strip() or "Must Have"
            classified.append({
                "id": req_id,
                "text": feature,
                "priority": priority,
            })

        # Step 3: Refine (Must-Have only)
        print("\nStep 3/4: 逐条精化 — 仅 Must Have 项\n")
        functional = []
        for item in classified:
            if item["priority"] == "Must Have":
                print(f'关于"{item["text"]}"，请补充关键细节：')
                q1 = input("1. 具体支持哪些操作或场景？").strip()
                q2 = input("2. 需要处理哪些异常情况？").strip()
                q3 = input("3. 有什么性能或安全约束？").strip()
                assembled = f"{item['text']}，{q1}，{q2}，{q3}"
                print(f"\n系统自动组装为完整需求：\n{assembled}\n")
                functional.append({
                    "id": item["id"],
                    "text": assembled,
                    "priority": item["priority"],
                    "gherkin_count": 1,
                })
            else:
                functional.append({
                    "id": item["id"],
                    "text": item["text"],
                    "priority": item["priority"],
                    "gherkin_count": 0,
                })

        # Step 4: Non-functional
        print("\nStep 4/4: 非功能需求（输入 done 结束）")
        non_functional = []
        nfr_counter = 1
        while True:
            nfr_id = input("需求ID：").strip()
            if nfr_id.lower() == "done":
                break
            if not nfr_id:
                nfr_id = f"NFR-{nfr_counter:03d}"
            text = input("需求描述：").strip()
            non_functional.append({"id": nfr_id, "text": text})
            nfr_counter += 1
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

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        """Check requirements meet minimum standard."""
        functional = data.get("functional", [])
        non_functional = data.get("non_functional", [])

        if not functional:
            return False, "至少需要 1 条功能需求"

        missing_priority = [req["id"] for req in functional if not req.get("priority")]
        if missing_priority:
            return False, f"以下需求缺少优先级: {', '.join(missing_priority)}"

        if not non_functional:
            return False, "至少需要 1 条非功能需求"

        return True, "Requirements 最低标准已满足"
