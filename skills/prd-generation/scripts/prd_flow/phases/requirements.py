"""Atomic requirements and release-scope collection."""
from typing import Any

from prd_flow.phases.base import Phase


class RequirementsPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P3"

    @property
    def phase_name(self) -> str:
        return "Requirements"

    def run(self) -> dict[str, Any]:
        print("\n[Requirements] 每行一个原子需求，输入 done 结束。\n")
        functional: list[dict] = []
        while True:
            text = input("功能需求：").strip()
            if text.lower() == "done":
                break
            functional.append({
                "id": f"REQ-{len(functional) + 1:03d}",
                "text": text,
                "priority": input("优先级（Must Have/Should Have/Could Have）：").strip() or "Must Have",
                "release_scope": input("版本范围（current/out_of_version/not_applicable）：").strip() or "current",
                "requirement_kind": "atomic",
            })

        non_functional: list[dict] = []
        while True:
            text = input("非功能需求（done 结束）：").strip()
            if text.lower() == "done":
                break
            non_functional.append({
                "id": f"NFR-{len(non_functional) + 1:03d}",
                "text": text,
                "release_scope": input("版本范围（current/out_of_version/not_applicable）：").strip() or "current",
                "requirement_kind": "atomic",
            })
        return self.collect(functional, non_functional)

    def collect(self, functional: list[dict], non_functional: list[dict]) -> dict:
        for item in [*functional, *non_functional]:
            item.setdefault("release_scope", "current")
            item.setdefault("requirement_kind", "atomic")
        data = {"functional": functional, "non_functional": non_functional}
        self.update_state(data)
        return data

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        functional = data.get("functional", [])
        non_functional = data.get("non_functional", [])
        if not functional:
            return False, "至少需要 1 条功能需求"
        missing_priority = [r.get("id", "UNKNOWN") for r in functional if not r.get("priority")]
        if missing_priority:
            return False, f"以下需求缺少优先级: {', '.join(missing_priority)}"
        if not non_functional:
            return False, "至少需要 1 条非功能需求"
        valid_scopes = {"current", "out_of_version", "not_applicable"}
        invalid_scope = [r.get("id", "UNKNOWN") for r in [*functional, *non_functional] if r.get("release_scope", "current") not in valid_scopes]
        if invalid_scope:
            return False, f"以下需求的 release_scope 无效: {', '.join(invalid_scope)}"
        non_atomic = [r.get("id", "UNKNOWN") for r in [*functional, *non_functional] if r.get("release_scope", "current") == "current" and r.get("requirement_kind", "atomic") != "atomic"]
        if non_atomic:
            return False, f"当前版本规范性需求必须原子化: {', '.join(non_atomic)}"
        return True, "需求均有稳定 ID、版本范围且当前版本条款已原子化"
