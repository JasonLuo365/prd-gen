"""Shared utility functions for PRD Flow."""


def generate_doc_id(project_name: str) -> str:
    """Generate document ID from project name."""
    base = project_name.upper().replace(" ", "-").replace("_", "-")
    return f"{base}-v1.0"
