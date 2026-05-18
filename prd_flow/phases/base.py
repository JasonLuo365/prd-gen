"""Abstract base class for PRD generation phases."""
from abc import ABC, abstractmethod
from typing import Any

from prd_flow.session import SessionState


class Phase(ABC):
    """Base class for all PRD generation phases."""

    def __init__(self, state: SessionState):
        self.state = state

    @property
    @abstractmethod
    def phase_id(self) -> str:
        """Unique phase identifier (e.g., 'P1', 'P2')."""
        ...

    @property
    @abstractmethod
    def phase_name(self) -> str:
        """Human-readable phase name."""
        ...

    @abstractmethod
    def run(self) -> dict[str, Any]:
        """Execute the phase and return collected data.

        In the actual implementation, this would interact with the user.
        For testing, we provide a programmatic interface.
        """
        ...

    def update_state(self, data: dict[str, Any]) -> None:
        """Update session state with collected data."""
        self.state.draft_content[self.phase_id] = data
        if self.phase_id not in self.state.completed_phases:
            self.state.completed_phases.append(self.phase_id)
