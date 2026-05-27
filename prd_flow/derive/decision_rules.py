"""Decision rules for Derive mode: fuzzy matching and orphan resolution."""

import logging

EDIT_DISTANCE_THRESHOLD = 2


def levenshtein_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Uses standard dynamic programming with O(min(m, n)) space optimization.
    """
    if len(a) < len(b):
        a, b = b, a

    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    current_row = [0] * (len(b) + 1)

    for i, char_a in enumerate(a):
        current_row[0] = i + 1

        for j, char_b in enumerate(b):
            # Cost: 0 if characters match, 1 otherwise
            cost = 0 if char_a == char_b else 1
            current_row[j + 1] = min(
                current_row[j] + 1,      # deletion
                previous_row[j + 1] + 1,  # insertion
                previous_row[j] + cost,   # substitution
            )

        previous_row, current_row = current_row, previous_row

    return previous_row[len(b)]


def find_best_module_match(target: str, available_modules: list[str]) -> str | None:
    """Find the closest module name to target using edit distance.

    Returns the closest match if the minimum distance is <= 2.
    Returns None if no match is within threshold or if available_modules is empty.
    Logs a warning when auto-correcting a non-exact match.
    """
    if not available_modules:
        return None

    best_match = None
    best_distance = float("inf")

    for module in available_modules:
        distance = levenshtein_distance(target, module)
        if distance < best_distance:
            best_distance = distance
            best_match = module

    if best_distance > EDIT_DISTANCE_THRESHOLD:
        return None

    if best_distance > 0 and best_match is not None:
        logging.warning(
            "Auto-correcting module name '%s' -> '%s' (edit distance=%s)",
            target,
            best_match,
            best_distance,
        )

    return best_match


def resolve_orphan_requirements(orphan_requirements: list[dict]) -> list[dict]:
    """Resolve orphan requirements by marking them as tentative.

    Returns copies of each requirement with ``"tentative": True`` added.
    This is the default "Option A" behavior for Derive mode.
    """
    resolved = []
    for req in orphan_requirements:
        req_copy = dict(req)
        req_copy["tentative"] = True
        resolved.append(req_copy)
    return resolved
