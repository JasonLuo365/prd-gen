"""Automatic quality fixers for Derive mode requirements."""

__all__ = [
    "fix_vague_quantifiers",
    "fix_measurable",
    "fix_parent_req",
]

def fix_vague_quantifiers(req: dict) -> dict:
    """Do not repair vague business language without an explicit source oracle."""
    return req


def fix_measurable(req: dict) -> dict:
    """Preserve measurable criteria without inventing thresholds.

    Derive mode can only carry metrics that are already present in the parent
    PRD or architecture package. Missing metrics are a quality/authority gap,
    not something this fixer may fill with defaults.
    """
    return req


def _word_overlap(text_a: str, text_b: str) -> float:
    """Compute word overlap similarity between two texts."""
    words_a = set(text_a.split())
    words_b = set(text_b.split())

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def fix_parent_req(req: dict, parent_requirements: list[dict]) -> dict:
    """Link a requirement to its best-matching parent requirement by word overlap."""
    if "parent_req" in req:
        return req

    text = req.get("text", "")
    best_score = 0.0
    best_parent_id = None

    for parent in parent_requirements:
        parent_text = parent.get("text", "")
        score = _word_overlap(text, parent_text)
        if score > best_score:
            best_score = score
            best_parent_id = parent.get("id")

    if best_score >= 0.3 and best_parent_id is not None:
        return {**req, "parent_req": best_parent_id}

    return req
