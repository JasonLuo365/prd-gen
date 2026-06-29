"""Detect whether to use Root or Derive mode."""
from enum import Enum, auto


class Mode(Enum):
    ROOT = auto()
    DERIVE = auto()


# Keywords that indicate explicit project beginning
_ROOT_KEYWORDS = ["新项目", "新功能", "从零开始", "开端", "开始", "立项"]


def detect_mode(
    user_input: str,
    parent_prd: str | None,
    parent_architecture: str | None,
    target_module: str | None,
    architecture_package: str | None = None,
) -> Mode:
    """Detect PRD generation mode from user input and context.

    Priority:
    1. User explicitly declares project beginning -> ROOT
    2. All derive inputs present -> DERIVE
    3. Otherwise -> ROOT
    """
    # Rule 1: Explicit root declaration (highest priority)
    if any(kw in user_input for kw in _ROOT_KEYWORDS):
        return Mode.ROOT

    # Rule 2: Derive mode requires parent PRD, architecture input, and target module
    if parent_prd and (parent_architecture or architecture_package) and target_module:
        return Mode.DERIVE

    # Rule 3: Default to root
    return Mode.ROOT
