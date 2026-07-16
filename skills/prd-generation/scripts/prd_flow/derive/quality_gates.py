"""Correctness gates for Derive-mode child PRDs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeriveQualityResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def check_parent_traceability(functional: list[dict]) -> DeriveQualityResult:
    """Every derived functional requirement must cite a parent requirement."""
    errors = [
        f"{req.get('id', 'UNKNOWN')} has no parent_req trace."
        for req in functional
        if not req.get("parent_req")
    ]
    return DeriveQualityResult(passed=not errors, errors=errors, warnings=[])
