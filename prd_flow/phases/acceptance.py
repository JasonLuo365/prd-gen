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

    def _split_when(self, text: str) -> tuple[str, list[str]]:
        """Split operation text into when steps.

        Splits by Chinese comma, English comma, or the word '并'.
        Returns (first_step, [and_steps]).
        """
        # Try splitting by Chinese comma first, then English comma, then '并'
        for sep in ("，", ",", "并"):
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts[0], parts[1:]
        return text, []

    def _build_scenario_dict(
        self,
        feature: str,
        scenario: str,
        given: str,
        when_text: str,
        then: str,
    ) -> dict:
        """Build a scenario dict from guided inputs."""
        when, and_steps = self._split_when(when_text)
        data = {
            "feature": feature,
            "scenario": scenario,
            "given": given,
            "when": when,
            "then": then,
        }
        if and_steps:
            data["and_steps"] = and_steps
        return data

    def _preview_gherkin(self, scenario: dict) -> str:
        """Generate a Gherkin preview string for a scenario."""
        lines = [f"  Scenario: {scenario['scenario']}"]
        lines.append(f"    Given {scenario['given']}")
        lines.append(f"    When {scenario['when']}")
        for step in scenario.get("and_steps", []):
            lines.append(f"    And {step}")
        lines.append(f"    Then {scenario['then']}")
        return "\n".join(lines)

    def run(self) -> dict[str, Any]:
        """Interactive entry point using guided questioning."""
        print("\n[Phase 4/5] Acceptance - 验收标准\n")

        scenarios = []
        while True:
            scenario_name = input("请描述一个场景名称：").strip()
            if scenario_name.lower() == "done":
                break

            feature_input = input("Feature 名称（默认: 通用功能）：").strip()
            feature = feature_input if feature_input else "通用功能"

            given = input("用户当前处于什么状态？").strip()
            when_text = input("用户做了什么操作？").strip()
            then = input("系统应该有什么反应？").strip()

            scenario = self._build_scenario_dict(
                feature=feature,
                scenario=scenario_name,
                given=given,
                when_text=when_text,
                then=then,
            )

            print("\n系统自动转化为：")
            print(self._preview_gherkin(scenario))
            print()

            confirm = input("是否确认？（y/n，直接输入修改内容则替换整行）：").strip()
            if confirm.lower() in ("y", "yes", "是"):
                scenarios.append(scenario)
                print(f"已添加 {len(scenarios)} 个场景。\n")
            elif confirm.lower() in ("n", "no", "否"):
                print("已放弃此场景，请重新输入。\n")
                continue
            else:
                # Treat as replacement for the When line
                scenario["when"] = confirm
                # Re-split in case the replacement also has commas
                new_when, new_and_steps = self._split_when(confirm)
                scenario["when"] = new_when
                if new_and_steps:
                    scenario["and_steps"] = new_and_steps
                else:
                    scenario.pop("and_steps", None)
                scenarios.append(scenario)
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

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        """Check each Must-Have requirement has at least 1 Gherkin scenario."""
        p3_data = self.state.draft_content.get("P3", {})
        functional = p3_data.get("functional", [])
        must_have_ids = {req["id"] for req in functional if req.get("priority") == "Must Have"}

        if not must_have_ids:
            return True, "无 Must-Have 需求，跳过 Gherkin 检查"

        scenarios = data.get("scenarios", [])
        covered_ids = {s["req_id"] for s in scenarios if s.get("req_id")}

        uncovered = must_have_ids - covered_ids
        if uncovered:
            return False, f"以下 Must-Have 需求缺少 Gherkin 场景: {', '.join(sorted(uncovered))}"

        return True, "Acceptance 最低标准已满足"
