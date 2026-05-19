"""Build derive mode context from parent documents."""
from pathlib import Path

import yaml

from prd_flow.derive.parser import extract_module_context, parse_parent_prd


def build_derive_context(parent_prd_path: Path, parent_arch_path: Path, target_module: str) -> dict:
    """Build complete context for Derive mode.

    Returns:
        {
            "success": bool,
            "parent_doc_id": str,
            "parent_arch_id": str,
            "module_name": str,
            "module": dict | None,
            "related_requirements": list[dict],
            "interfaces": list[dict],
            "dependencies": list[dict],
            "error": str | None,
            "available_modules": list[str],
        }
    """
    # 1. Parse parent PRD
    parent_prd = parse_parent_prd(parent_prd_path)
    parent_doc_id = parent_prd.get("doc_id", "UNKNOWN")

    # 2. Extract module context from architecture
    arch_result = extract_module_context(parent_arch_path, target_module)

    if not arch_result["found"]:
        return {
            "success": False,
            "parent_doc_id": parent_doc_id,
            "parent_arch_id": "UNKNOWN",
            "module_name": target_module,
            "module": None,
            "related_requirements": [],
            "interfaces": [],
            "dependencies": [],
            "error": f"模块 '{target_module}' 不存在于架构设计中",
            "available_modules": arch_result["available_modules"],
        }

    module = arch_result["module"]
    module_name = module.get("name", target_module)

    # 3. Extract related requirements from parent PRD
    # 匹配规则：需求文本中包含模块名，或模块的接口名出现在需求中
    all_requirements = parent_prd.get("requirements", [])
    related_requirements = []
    module_keywords = [module_name]
    for interface in module.get("interfaces", []):
        if isinstance(interface, dict) and "name" in interface:
            module_keywords.append(interface["name"])

    for req in all_requirements:
        req_text = req.get("text", "")
        if any(kw in req_text for kw in module_keywords):
            related_requirements.append(req)

    # 4. Extract interfaces and dependencies
    interfaces = module.get("interfaces", []) if isinstance(module, dict) else []
    dependencies = module.get("dependencies", []) if isinstance(module, dict) else []

    # 从架构文档中提取 arch_id（如果有）
    arch_content = parent_arch_path.read_text(encoding="utf-8")
    arch_data = yaml.safe_load(arch_content) or {}
    parent_arch_id = arch_data.get("doc_id", "UNKNOWN") if isinstance(arch_data, dict) else "UNKNOWN"

    return {
        "success": True,
        "parent_doc_id": parent_doc_id,
        "parent_arch_id": parent_arch_id,
        "module_name": module_name,
        "module": module,
        "related_requirements": related_requirements,
        "interfaces": interfaces if isinstance(interfaces, list) else [],
        "dependencies": dependencies if isinstance(dependencies, list) else [],
        "error": None,
        "available_modules": arch_result["available_modules"],
    }
