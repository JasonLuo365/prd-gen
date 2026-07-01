"""Build derive mode context from parent PRD and architecture package."""
from __future__ import annotations

import re
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
        if any(keyword and keyword in req_text for keyword in module_keywords) or _semantic_match(req, module):
            related_requirements.append(req)

    related_non_functional = []
    for nfr in parent_prd.get("non_functional", []):
        nfr_text = _normalize_keyword(nfr.get("text", ""))
        if any(keyword and keyword in nfr_text for keyword in module_keywords) or _semantic_match(nfr, module):
            related_non_functional.append(nfr)

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
        "related_non_functional": related_non_functional,
        "orphan_requirements": orphan_requirements,
        "interfaces": interfaces if isinstance(interfaces, list) else [],
        "dependencies": dependencies if isinstance(dependencies, list) else [],
        "error": None,
        "available_modules": arch_result.get("available_modules", []),
        "target_granularity": arch_result.get("target_granularity", target_granularity),
        "source_files": arch_result.get("source_files", []),
    }


def _module_keywords(module: dict) -> list[str]:
    keywords: list[str] = [module.get("name", ""), module.get("responsibility", "")]
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


_STOP_TERMS = {
    "系统",
    "模块",
    "支持",
    "提供",
    "管理",
    "学生",
    "数据",
    "中心",
    "生命周期",
    "接口",
    "统一",
    "核心",
    "职责",
}


def _semantic_match(req: dict, module: dict) -> bool:
    """Match Chinese parent requirements to module responsibility text.

    Architecture packages often name modules in English while root PRDs describe
    behavior in Chinese. A narrow character n-gram overlap on the module's
    responsibility gives Derive enough ownership signal without requiring a
    Leaf Gate report or manual mapping.
    """
    req_text = req.get("text", "")
    responsibility = module.get("responsibility", "")
    if _violates_module_ownership(req_text, responsibility):
        return False
    if _matches_responsibility_concept(req_text, responsibility):
        return True

    terms = _semantic_terms(module)
    if not terms:
        return False

    return any(len(term) >= 4 and term in req_text for term in terms)


def _violates_module_ownership(req_text: str, responsibility: str) -> bool:
    if _is_identity_requirement(req_text) and not _owns_identity(responsibility):
        return True
    if _is_retention_or_training_requirement(req_text):
        return not _owns_compliance(responsibility)
    if _is_tutoring_session_gate_requirement(req_text):
        return not _owns_tutoring_session(responsibility)
    if _is_problem_intake_requirement(req_text) and not _owns_problem_intake(responsibility):
        return True
    if _is_privacy_prompt_requirement(req_text) and not _owns_problem_intake(responsibility):
        return True
    return _violates_generation_ownership(req_text, responsibility)


def _violates_generation_ownership(req_text: str, responsibility: str) -> bool:
    """Prevent content-generation requirements from matching intake-style modules."""
    if _is_prompt_content_requirement(req_text) and not _owns_ai_tutoring(responsibility):
        return True
    if _is_solution_content_requirement(req_text) and not _owns_ai_tutoring(responsibility):
        return True

    generation_markers = ("完整解答", "分层提示", "关键推导", "标准术语")
    if not any(marker in req_text for marker in generation_markers):
        return False

    if "标准术语" in req_text or "关键推导" in req_text:
        owner_markers = ("完整解答", "分层提示", "提示模板", "LLM")
        return not any(marker in responsibility for marker in owner_markers)

    owner_markers = ("完整解答", "分层提示", "解答请求", "提示轮次", "提示模板", "LLM")
    return not any(marker in responsibility for marker in owner_markers)


def _matches_responsibility_concept(req_text: str, responsibility: str) -> bool:
    if _owns_identity(responsibility):
        return (
            ("手机号" in req_text and ("登录" in req_text or "验证码" in req_text))
            or ("验证码" in req_text and any(marker in req_text for marker in ("生成", "有效", "重发", "输错", "失效")))
        )

    if _owns_problem_intake(responsibility):
        return (
            _is_problem_intake_requirement(req_text)
            or _is_privacy_prompt_requirement(req_text)
        )

    if _owns_tutoring_session(responsibility):
        return (
            ("基础水平" in req_text and any(marker in req_text for marker in ("选择", "开始答疑", "未选择")))
            or _is_tutoring_session_gate_requirement(req_text)
            or ("完整解答" in req_text and any(marker in req_text for marker in ("查看", "点击", "按钮", "请求", "展示")))
            or ("会话" in req_text and any(marker in req_text for marker in ("启动", "开始", "关闭", "结束", "生命周期", "状态")))
        )

    if _owns_ai_tutoring(responsibility):
        return (
            _is_prompt_content_requirement(req_text)
            or _is_solution_content_requirement(req_text)
            or ("提示" in req_text and "标准术语" in req_text)
        )

    if _owns_compliance(responsibility):
        return _is_retention_or_training_requirement(req_text)

    return False


def _owns_identity(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("手机号登录", "短信验证码", "认证会话"))


def _owns_problem_intake(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("图片上传", "格式/大小", "有效数学题识别", "图片元数据", "隐私提示"))


def _owns_tutoring_session(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("基础水平选择", "会话生命周期", "提示轮次计数", "解答请求门控"))


def _owns_ai_tutoring(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("生成分层提示", "完整解答", "LLM", "提示模板"))


def _owns_compliance(responsibility: str) -> bool:
    return any(marker in responsibility for marker in ("保留策略", "定时删除", "合规审计", "训练使用禁止"))


def _is_identity_requirement(req_text: str) -> bool:
    return "验证码" in req_text or ("手机号" in req_text and "登录" in req_text)


def _is_problem_intake_requirement(req_text: str) -> bool:
    if "图片" not in req_text:
        return False
    return any(
        marker in req_text
        for marker in ("上传", "JPG", "PNG", "10MB", "损坏", "有效高中数学题", "识别", "最多", "第 4 张", "第4张")
    )


def _is_privacy_prompt_requirement(req_text: str) -> bool:
    return "隐私提示" in req_text and ("上传前" in req_text or "展示" in req_text)


def _is_retention_or_training_requirement(req_text: str) -> bool:
    if _is_privacy_prompt_requirement(req_text):
        return False
    return any(marker in req_text for marker in ("30 天", "30天", "删除", "不可读取", "保存时间", "保留", "模型训练"))


def _is_tutoring_session_gate_requirement(req_text: str) -> bool:
    if "基础水平" in req_text and any(marker in req_text for marker in ("选择", "开始答疑", "未选择")):
        return "生成分层提示" not in req_text
    if ("分层提示" in req_text or "提示轮次" in req_text) and any(
        marker in req_text for marker in ("轮次", "上限", "成功展示", "失败不计入")
    ):
        return True
    if "提示轮次" in req_text and "记录" in req_text:
        return True
    if "完整解答" in req_text and any(marker in req_text for marker in ("查看", "点击", "按钮", "请求")):
        return not any(marker in req_text for marker in ("生成响应", "按步骤", "关键推导", "标准术语"))
    return False


def _is_prompt_content_requirement(req_text: str) -> bool:
    if "分层提示" not in req_text and "提示" not in req_text:
        return False
    return any(
        marker in req_text
        for marker in ("生成分层提示", "提示生成", "生成提示", "每一轮分层提示", "提示方向", "追问问题", "关键计算结果", "前置知识", "关键思路", "突破口", "易错提醒")
    )


def _is_solution_content_requirement(req_text: str) -> bool:
    if "完整解答" not in req_text:
        return False
    return any(marker in req_text for marker in ("生成响应", "生成", "按步骤", "关键推导", "标准术语"))


def _semantic_terms(module: dict) -> set[str]:
    source_parts = [
        module.get("responsibility", ""),
        module.get("partition_reason", ""),
        " ".join(module.get("included_contexts", [])),
    ]
    terms: set[str] = set()
    for text in source_parts:
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if chunk in _STOP_TERMS:
                continue
            if 2 <= len(chunk) <= 8:
                terms.add(chunk)
            for size in (4,):
                for index in range(0, max(len(chunk) - size + 1, 0)):
                    term = chunk[index:index + size]
                    if term not in _STOP_TERMS:
                        terms.add(term)

    return terms
