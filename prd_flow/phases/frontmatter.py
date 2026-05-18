"""Frontmatter metadata collection phase."""
from datetime import datetime

from prd_flow.phases.base import Phase
from prd_flow.session import SessionState
from prd_flow.utils import generate_doc_id


class FrontmatterPhase(Phase):
    @property
    def phase_id(self) -> str:
        return "P1"

    @property
    def phase_name(self) -> str:
        return "Frontmatter"

    def run(self):
        """Interactive entry point."""
        # In real usage, this would prompt the user interactively
        raise NotImplementedError("Use collect() for programmatic input")

    def collect(
        self,
        project_name: str,
        author: str = "Claude",
        priority: str = "P0",
        tags: list[str] | None = None,
    ) -> dict:
        """Collect frontmatter data programmatically."""
        doc_id = generate_doc_id(project_name)

        data = {
            "doc_id": doc_id,
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

    def _get_parent_doc(self) -> str | None:
        """Get parent document ID from context."""
        if self.state.mode == "derive" and self.state.parent_context:
            return self.state.parent_context.get("parent_doc_id")
        return None
