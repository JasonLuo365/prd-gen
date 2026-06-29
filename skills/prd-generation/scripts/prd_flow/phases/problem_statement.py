"""Problem Statement phase for PRD generation."""
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState


class ProblemStatementPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P2"

    @property
    def phase_name(self) -> str:
        return "Problem Statement"

    def run(self) -> dict[str, Any]:
        """Interactive entry point."""
        print("\n[Phase 2/5] Problem Statement - 问题陈述\n")
        target_users = input("目标用户：").strip()
        pain_points = input("痛点描述：").strip()
        opportunity = input("机会窗口：").strip()
        return self.collect(target_users=target_users, pain_points=pain_points, opportunity=opportunity)

    def collect(
        self,
        target_users: str,
        pain_points: str,
        opportunity: str,
    ) -> dict:
        """Collect problem statement data programmatically."""
        data = {
            "target_users": target_users,
            "pain_points": pain_points,
            "opportunity": opportunity,
        }
        self.update_state(data)
        return data

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        """Check problem statement has all required fields non-empty."""
        required = ["target_users", "pain_points", "opportunity"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return False, f"缺少必填内容: {', '.join(missing)}"
        return True, "Problem Statement 最低标准已满足"
