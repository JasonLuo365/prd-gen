"""Build derive mode context from parent PRD and architecture package."""
from __future__ import annotations

from pathlib import Path

from prd_flow.derive.parser import extract_module_context, parse_parent_prd


def build_derive_context(
    parent_prd_path: Path,
    architecture_package_path: Path,
    target_module: str,
    target_granularity: str = "auto",
) -> dict:
    """Build complete context for Derive mode."""
    parent_prd = parse_parent_prd(parent_prd_path)
    parent_doc_id = parent_prd.get("doc_id", "UNKNOWN")

    arch_result = extract_module_context(
        architecture_package_path,
        target_module,
        target_granularity=target_granularity,
    )

    if not arch_result["found"]:
        return {
            "success": False,
            "parent_doc_id": parent_doc_id,
            "parent_arch_id": arch_result.get("parent_arch_id", "UNKNOWN"),
            "module_name": target_module,
            "module": None,
            "related_requirements": [],
            "interfaces": [],
            "dependencies": [],
            "orphan_requirements": [],
            "error": arch_result.get("error") or f"Module '{target_module}' was not found in the architecture input.",
            "available_modules": arch_result.get("available_modules", []),
            "target_granularity": arch_result.get("target_granularity", target_granularity),
            "source_files": arch_result.get("source_files", []),
        }

    module = arch_result["module"]
    module_name = module.get("name", target_module)

    all_requirements = parent_prd.get("requirements", [])
    module_keywords = _module_keywords(module)
    related_requirements = []
    for req in all_requirements:
        req_text = _normalize_keyword(req.get("text", ""))
        if any(keyword and keyword in req_text for keyword in module_keywords):
            related_requirements.append(req)

    all_modules_keywords = [_normalize_keyword(item) for item in arch_result.get("available_modules", [])]
    orphan_requirements = []
    for req in all_requirements:
        req_text = _normalize_keyword(req.get("text", ""))
        if not any(keyword and keyword in req_text for keyword in all_modules_keywords):
            orphan_requirements.append(req)

    interfaces = module.get("interfaces", []) if isinstance(module, dict) else []
    dependencies = module.get("dependencies", []) if isinstance(module, dict) else []

    return {
        "success": True,
        "parent_doc_id": parent_doc_id,
        "parent_arch_id": arch_result.get("parent_arch_id", "UNKNOWN"),
        "module_name": module_name,
        "module": module,
        "related_requirements": related_requirements,
        "orphan_requirements": orphan_requirements,
        "interfaces": interfaces if isinstance(interfaces, list) else [],
        "dependencies": dependencies if isinstance(dependencies, list) else [],
        "error": None,
        "available_modules": arch_result.get("available_modules", []),
        "target_granularity": arch_result.get("target_granularity", target_granularity),
        "source_files": arch_result.get("source_files", []),
    }


def _module_keywords(module: dict) -> list[str]:
    keywords: list[str] = [module.get("name", "")]
    keywords.extend(module.get("included_contexts", []))
    for interface in module.get("interfaces", []):
        if isinstance(interface, dict):
            keywords.append(interface.get("name", ""))
    for dependency in module.get("dependencies", []):
        if isinstance(dependency, dict):
            keywords.append(dependency.get("name", ""))
    return [_normalize_keyword(keyword) for keyword in keywords if keyword]


def _normalize_keyword(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())
