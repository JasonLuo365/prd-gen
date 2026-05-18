"""Parse parent PRD and architecture documents for Derive mode."""
import re
from pathlib import Path

import yaml


def parse_parent_prd(path: Path) -> dict:
    """Parse a parent PRD document and extract structured data."""
    content = path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    frontmatter = {}
    if content.startswith("---"):
        _, fm, body = content.split("---", 2)
        frontmatter = yaml.safe_load(fm)
        content = body

    # Extract requirements
    requirements = []
    req_pattern = r"- \[(REQ-\d+)\] (.+?)(?=\n- \[|\n## |\Z)"
    for match in re.finditer(req_pattern, content, re.DOTALL):
        req_id = match.group(1)
        req_text = match.group(2).strip()
        requirements.append({"id": req_id, "text": req_text})

    return {
        "doc_id": frontmatter.get("doc_id", "UNKNOWN"),
        "frontmatter": frontmatter,
        "requirements": requirements,
        "raw_content": content,
    }


def extract_module_context(arch_path: Path, target_module: str) -> dict:
    """Extract context for a specific module from architecture document."""
    content = arch_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    modules = data.get("modules", [])
    available = [m["name"] for m in modules]

    for module in modules:
        if module["name"] == target_module:
            return {
                "found": True,
                "module": module,
                "available_modules": available,
            }

    return {
        "found": False,
        "module": None,
        "available_modules": available,
    }
