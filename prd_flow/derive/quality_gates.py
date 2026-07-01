"""Quality gates for focused Derive-mode child PRDs."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MUST_WARNING_LIMIT = 6
DEFAULT_MUST_BLOCK_LIMIT = 8


@dataclass(frozen=True)
class DeriveQualityResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def check_derive_scope_budget(
    functional: list[dict],
    warning_limit: int = DEFAULT_MUST_WARNING_LIMIT,
    block_limit: int = DEFAULT_MUST_BLOCK_LIMIT,
) -> DeriveQualityResult:
    """Check whether a child PRD is small enough to remain focused.

    The warning limit is advisory. The block limit is intentionally strict:
    Derive should narrow a parent node, not recreate a broad root-style PRD.
    """
    must_count = sum(1 for req in functional if req.get("priority") == "Must Have")
    warnings: list[str] = []
    errors: list[str] = []

    if must_count > warning_limit:
        warnings.append(
            f"Must Have count {must_count} exceeds focused derive warning budget {warning_limit}."
        )
    if must_count > block_limit:
        errors.append(
            f"Must Have count {must_count} exceeds focused derive block budget {block_limit}; "
            "narrow the target module or merge requirements before generating child PRD."
        )

    return DeriveQualityResult(passed=not errors, errors=errors, warnings=warnings)


def check_parent_traceability(functional: list[dict]) -> DeriveQualityResult:
    """Every derived functional requirement must cite a parent requirement."""
    errors = [
        f"{req.get('id', 'UNKNOWN')} has no parent_req trace."
        for req in functional
        if not req.get("parent_req")
    ]
    return DeriveQualityResult(passed=not errors, errors=errors, warnings=[])
