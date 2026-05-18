"""Session state management for PRD generation workflow."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionState:
    """Represents the current state of a PRD generation session."""

    session_id: str
    mode: str  # "root" | "derive"
    current_phase: str
    completed_phases: list[str]
    draft_content: dict[str, Any]
    parent_context: dict[str, Any] | None = None
    target_module: str | None = None


def save_session(state: SessionState, path: Path) -> None:
    """Save session state to a JSON file."""
    path.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False))


def load_session(path: Path) -> SessionState:
    """Load session state from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return SessionState(**data)
