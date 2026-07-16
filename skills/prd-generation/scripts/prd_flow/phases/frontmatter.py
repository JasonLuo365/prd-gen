"""Frontmatter metadata collection phase."""
from datetime import datetime
from typing import Any

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState
from prd_flow.utils import generate_doc_id


def _stable_refs(items: list[Any] | None, keys: tuple[str, ...]) -> list[str]:
    """Return ordered, deduplicated identifiers without embedding full records."""
    refs: list[str] = []
    for item in items or []:
        ref: Any = item if isinstance(item, str) else None
        if isinstance(item, dict):
            ref = next((item.get(key) for key in keys if item.get(key)), None)
        if ref is None:
            continue
        normalized = str(ref).strip()
        if normalized and normalized not in refs:
            refs.append(normalized)
    return refs


class FrontmatterPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P1"

    @property
    def phase_name(self) -> str:
        return "Frontmatter"

    def run(self) -> dict[str, Any]:
        """Interactive entry point."""
        print("\n[Phase 1/5] Frontmatter - 文档元数据\n")
        if self.state.mode == "derive":
            if not self.state.parent_context:
                raise ValueError("Derive mode requires parent_context to be set.")
            required_keys = {"parent_doc_id", "parent_arch_id", "module_name", "interfaces", "dependencies"}
            missing = required_keys - self.state.parent_context.keys()
            if missing:
                raise ValueError(f"Derive mode parent_context missing keys: {missing}")
            return self.collect_derive(
                parent_doc_id=self.state.parent_context["parent_doc_id"],
                parent_arch_id=self.state.parent_context.get("parent_arch_id"),
                module_name=self.state.parent_context["module_name"],
                interfaces=self.state.parent_context["interfaces"],
                dependencies=self.state.parent_context["dependencies"],
                events=self.state.parent_context.get("events", []),
                implementation_surfaces=self.state.parent_context.get("implementation_surfaces", []),
                priority="P0",
            )
        project_name = input("项目名称：").strip()
        author = input("作者（默认: Claude）：").strip() or "Claude"
        priority = input("优先级（P0/P1/P2, 默认: P0）：").strip() or "P0"
        return self.collect(project_name=project_name, author=author, priority=priority)

    def collect(
        self,
        project_name: str,
        author: str = "Claude",
        priority: str = "P0",
        tags: list[str] | None = None,
    ) -> dict:
        """Collect frontmatter data programmatically."""
        if self.state.mode == "derive":
            if not self.state.parent_context:
                raise ValueError("Derive mode requires parent_context to be set.")
            return self.collect_derive(
                parent_doc_id=self.state.parent_context["parent_doc_id"],
                parent_arch_id=self.state.parent_context.get("parent_arch_id"),
                module_name=self.state.parent_context["module_name"],
                interfaces=self.state.parent_context["interfaces"],
                dependencies=self.state.parent_context["dependencies"],
                events=self.state.parent_context.get("events", []),
                implementation_surfaces=self.state.parent_context.get("implementation_surfaces", []),
                priority=priority,
                author=author,
            )

        doc_id = generate_doc_id(project_name)

        data = {
            "doc_id": doc_id,
            "project_name": project_name,
            "version": "1.0.0",
            "layer": self.state.mode,
            "parent_doc": self._get_parent_doc(),
            "author": author,
            "status": "draft",
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "tags": tags or [],
        }

        self.update_state(data)
        return data

    def collect_derive(
        self,
        parent_doc_id: str,
        parent_arch_id: str | None,
        module_name: str,
        interfaces: list[dict],
        dependencies: list[dict],
        events: list[dict] | None = None,
        implementation_surfaces: list[str] | None = None,
        priority: str = "P0",
        author: str = "Claude",
    ) -> dict:
        """Collect frontmatter data for derive mode programmatically."""
        module_suffix = module_name.upper().replace(" ", "-").replace("_", "-")
        doc_id = f"{parent_doc_id}-{module_suffix}-v1.0"
        resolved_parent_arch = parent_arch_id or f"{parent_doc_id}-ARCH"

        data = {
            "doc_id": doc_id,
            "version": "1.0.0",
            "layer": "derive",
            "parent_doc": parent_doc_id,
            "parent_arch": resolved_parent_arch,
            "module_name": module_name,
            "author": author,
            "status": "complete",
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "interface_refs": _stable_refs(interfaces, ("contract_id", "name", "path")),
            "dependency_refs": _stable_refs(dependencies, ("name", "module")),
            "event_refs": _stable_refs(events, ("contract_id", "event_name", "name")),
            "implementation_surfaces": implementation_surfaces or [],
            "inheritance_complete": True,
            "release_scope_frozen": True,
        }

        self.update_state(data)
        return data

    def check_minimum_standard(self, data: dict[str, Any]) -> tuple[bool, str]:
        """Check frontmatter has all required fields non-empty."""
        required = ["doc_id", "version", "author", "status", "priority"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return False, f"缺少必填字段: {', '.join(missing)}"
        return True, "Frontmatter 最低标准已满足"

    def _get_parent_doc(self) -> str | None:
        """Get parent document ID from context."""
        if self.state.mode == "derive" and self.state.parent_context:
            return self.state.parent_context.get("parent_doc_id")
        return None
