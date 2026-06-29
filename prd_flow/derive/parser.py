"""Parse parent PRD and architecture inputs for Derive mode."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from prd_flow import yaml_utils as yaml


STANDARD_ARCH_FILES = [
    "README.md",
    "01-system-overview.md",
    "02-module-partitioning.md",
    "03-runtime-architecture.md",
    "04-adr-summary.md",
    "05-data-model.md",
    "06-interface-contracts.md",
    "07-technology-choices.md",
    "08-deployment.md",
]

VALID_GRANULARITIES = {"auto", "deployable_module", "bounded_context"}

EXTERNAL_NAMES = [
    "Telegram Bot API",
    "Telegram",
    "PC OS / Applications",
    "PC OS / Apps",
    "PostgreSQL",
    "Redis",
    "Kafka",
    "RabbitMQ",
    "Redis Streams",
    "S3",
    "MinIO",
]


def parse_parent_prd(path: Path) -> dict:
    """Parse a parent PRD document and extract structured data."""
    content = path.read_text(encoding="utf-8")

    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            body = parts[2]
            loaded = yaml.safe_load(fm)
            if loaded is not None:
                frontmatter = loaded
            content = body

    requirements = []
    req_pattern = r"- \[(REQ-\d+)\] (.+?)(?=\n- \[|\n## |\Z)"
    for match in re.finditer(req_pattern, content, re.DOTALL):
        req_id = match.group(1)
        req_text = match.group(2).strip()
        requirements.append({"id": req_id, "text": req_text})

    return {
        "doc_id": frontmatter.get("doc_id", "UNKNOWN") if isinstance(frontmatter, dict) else "UNKNOWN",
        "frontmatter": frontmatter,
        "requirements": requirements,
        "raw_content": content,
    }


def extract_module_context(
    arch_path: Path,
    target_module: str,
    target_granularity: str = "auto",
) -> dict:
    """Extract context for a module from a legacy architecture file or package.

    `arch_path` may be one of:
    - legacy YAML architecture file with a top-level `modules` list;
    - architecture package directory;
    - README.md inside an architecture package;
    - zip file containing the architecture Markdown files.
    """
    if target_granularity not in VALID_GRANULARITIES:
        raise ValueError(f"Invalid target_granularity: {target_granularity}")

    source = _load_architecture_source(arch_path)
    if source["kind"] == "missing":
        return _not_found(target_module, [], source["error"], target_granularity)
    if source["kind"] == "legacy_yaml":
        return _extract_from_legacy_yaml(source, target_module, target_granularity)
    return _extract_from_markdown_package(source, target_module, target_granularity)


def _load_architecture_source(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "kind": "missing",
            "source_id": "UNKNOWN",
            "files": {},
            "error": f"Architecture input not found: {path}",
        }

    if path.is_file() and path.suffix.lower() == ".zip":
        return _read_zip_package(path)

    if path.is_dir():
        return _read_directory_package(path)

    content = _read_text(path)
    data = _try_load_yaml(content)
    if isinstance(data, dict) and isinstance(data.get("modules"), list):
        return {
            "kind": "legacy_yaml",
            "source_id": data.get("doc_id", path.stem),
            "path": str(path),
            "data": data,
            "files": {path.name: content},
        }

    if path.name.lower() == "readme.md":
        return _read_directory_package(path.parent, explicit_readme=path)

    return {
        "kind": "markdown_package",
        "source_id": path.stem,
        "path": str(path),
        "files": {path.name: content},
    }


def _read_directory_package(path: Path, explicit_readme: Path | None = None) -> dict[str, Any]:
    files: dict[str, str] = {}
    for name in STANDARD_ARCH_FILES:
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            files[name] = _read_text(candidate)

    if explicit_readme and explicit_readme.exists():
        files["README.md"] = _read_text(explicit_readme)

    if not files:
        for candidate in sorted(path.glob("*.md")):
            files[candidate.name] = _read_text(candidate)

    return {
        "kind": "markdown_package",
        "source_id": path.name or "ARCH-PACKAGE",
        "path": str(path),
        "files": files,
    }


def _read_zip_package(path: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.namelist() if not m.endswith("/")]
        markdown_members = [m for m in members if Path(m).suffix.lower() == ".md"]

        for name in STANDARD_ARCH_FILES:
            match = next((m for m in markdown_members if Path(m).name == name), None)
            if match:
                files[name] = archive.read(match).decode("utf-8", errors="replace")

        if not files:
            for member in markdown_members:
                member_path = Path(member)
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                files[member_path.name] = archive.read(member).decode("utf-8", errors="replace")

    return {
        "kind": "markdown_package",
        "source_id": path.stem,
        "path": str(path),
        "files": files,
    }


def _extract_from_legacy_yaml(source: dict[str, Any], target_module: str, target_granularity: str) -> dict:
    data = source["data"]
    modules = data.get("modules", [])
    available = [m["name"] for m in modules if isinstance(m, dict) and "name" in m]

    for module in modules:
        if isinstance(module, dict) and _same_name(module.get("name", ""), target_module):
            resolved = dict(module)
            resolved.setdefault("granularity", "module" if target_granularity == "auto" else target_granularity)
            return {
                "found": True,
                "module": resolved,
                "available_modules": available,
                "parent_arch_id": source["source_id"],
                "source_files": list(source.get("files", {}).keys()),
                "target_granularity": resolved["granularity"],
            }

    return _not_found(target_module, available, None, target_granularity)


def _extract_from_markdown_package(source: dict[str, Any], target_module: str, target_granularity: str) -> dict:
    files = source.get("files", {})
    deployable_modules = _parse_deployable_modules(files.get("02-module-partitioning.md", ""))
    bounded_contexts = _parse_bounded_contexts(files)

    candidates: list[dict[str, Any]] = []
    if target_granularity in ("auto", "deployable_module"):
        candidates.extend(deployable_modules)
    if target_granularity in ("auto", "bounded_context"):
        candidates.extend(bounded_contexts)

    available_modules = _unique(
        [item["name"] for item in deployable_modules]
        + [item["name"] for item in bounded_contexts]
    )

    exact_matches = [item for item in candidates if _same_name(item["name"], target_module)]
    if target_granularity == "auto" and len({item["granularity"] for item in exact_matches}) > 1:
        return _not_found(
            target_module,
            available_modules,
            f"Target module '{target_module}' matches multiple granularities; specify target_granularity.",
            target_granularity,
        )
    if not exact_matches:
        return _not_found(target_module, available_modules, None, target_granularity)

    module = dict(exact_matches[0])
    aliases = _module_aliases(module)
    all_names = _unique(available_modules + EXTERNAL_NAMES)
    module["interfaces"] = _extract_interfaces_for_target(files.get("06-interface-contracts.md", ""), aliases)
    module["dependencies"] = _extract_dependencies(files, aliases, all_names)
    module["evidence"] = _collect_relevant_snippets(files, aliases)
    module["source_files"] = list(files.keys())

    return {
        "found": True,
        "module": module,
        "available_modules": available_modules,
        "parent_arch_id": source.get("source_id", "ARCH-PACKAGE"),
        "source_files": list(files.keys()),
        "target_granularity": module["granularity"],
    }


def _parse_deployable_modules(content: str) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    for line in content.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 3 or not _has_bold(cells[0]):
            continue
        name = _clean_markdown(cells[0])
        if not _looks_like_module_name(name):
            continue
        modules.append(
            {
                "name": name,
                "granularity": "deployable_module",
                "included_contexts": _extract_possible_names(cells[1]),
                "responsibility": _clean_markdown(cells[2]),
                "partition_reason": _clean_markdown(cells[3]) if len(cells) > 3 else "",
            }
        )
    return _dedupe_modules(modules)


def _parse_bounded_contexts(files: dict[str, str]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []

    overview = files.get("01-system-overview.md", "")
    for line in overview.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) < 2 or not _has_bold(cells[0]):
            continue
        name = _clean_markdown(cells[0])
        if not _looks_like_module_name(name):
            continue
        contexts.append(
            {
                "name": name,
                "granularity": "bounded_context",
                "responsibility": _clean_markdown(cells[1]),
            }
        )

    data_model = files.get("05-data-model.md", "")
    for heading in re.findall(r"^###\s+(.+)$", data_model, re.MULTILINE):
        name = _clean_heading_title(heading)
        if _looks_like_module_name(name):
            contexts.append(
                {
                    "name": name,
                    "granularity": "bounded_context",
                    "responsibility": _find_section_first_table_text(data_model, heading),
                }
            )

    return _dedupe_modules(contexts)


def _extract_interfaces_for_target(content: str, aliases: list[str]) -> list[dict]:
    interfaces: list[dict] = []
    for level, heading, body in _iter_markdown_sections(content):
        if level not in (3, 4):
            continue
        block = f"{heading}\n{body}"
        if not _contains_any(block, aliases):
            continue
        errors = _unique(re.findall(r"`([A-Z][A-Z0-9_]+)`", block))
        interfaces.append(
            {
                "name": _clean_heading_title(heading) or "unknown",
                "source": "06-interface-contracts.md",
                "method": _extract_method(block),
                "error_codes": errors,
            }
        )
    return _dedupe_dicts_by_name(interfaces)


def _extract_dependencies(files: dict[str, str], aliases: list[str], all_names: list[str]) -> list[dict]:
    dependencies: list[dict] = []
    target_names = {_normalize_name(alias) for alias in aliases}
    for filename, content in files.items():
        for _level, heading, body in _iter_markdown_sections(content):
            block = f"{heading}\n{body}"
            if not _contains_any(block, aliases):
                continue
            for name in all_names:
                if _normalize_name(name) in target_names:
                    continue
                if _contains_any(block, [name]):
                    dependencies.append(
                        {
                            "name": name,
                            "source": filename,
                            "evidence": _clean_markdown(heading),
                        }
                    )
        for line in content.splitlines():
            if not _contains_any(line, aliases):
                continue
            for name in all_names:
                if _normalize_name(name) in target_names:
                    continue
                if _contains_any(line, [name]):
                    dependencies.append(
                        {
                            "name": name,
                            "source": filename,
                            "evidence": _clean_markdown(line).strip(),
                        }
                    )
    return _dedupe_dicts_by_name(dependencies)


def _collect_relevant_snippets(files: dict[str, str], aliases: list[str], limit: int = 40) -> list[dict]:
    snippets: list[dict] = []
    for filename, content in files.items():
        for line_no, line in enumerate(content.splitlines(), start=1):
            if _contains_any(line, aliases):
                snippets.append(
                    {
                        "source": filename,
                        "line": line_no,
                        "text": _clean_markdown(line).strip(),
                    }
                )
                if len(snippets) >= limit:
                    return snippets
    return snippets


def _iter_markdown_sections(content: str) -> list[tuple[int, str, str]]:
    matches = list(re.finditer(r"^(#{3,4})\s+(.+)$", content, re.MULTILINE))
    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append((len(match.group(1)), match.group(2).strip(), content[start:end]))
    return sections


def _find_section_first_table_text(content: str, heading: str) -> str:
    pattern = re.compile(rf"^###\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return ""
    next_heading = re.search(r"^###\s+", content[match.end():], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(content)
    section = content[match.end():end]
    for line in section.splitlines():
        cells = _split_markdown_row(line)
        if len(cells) >= 2 and not _is_table_separator(cells):
            return _clean_markdown(" ".join(cells))
    return ""


def _extract_method(text: str) -> str:
    method_match = re.search(r"\b(GET|POST|PUT|PATCH|DELETE|gRPC|WebSocket|HTTPS|event)\b", text, re.IGNORECASE)
    return method_match.group(1) if method_match else ""


def _module_aliases(module: dict[str, Any]) -> list[str]:
    aliases = [module["name"]]
    aliases.extend(module.get("included_contexts", []))
    return [alias for alias in _unique(aliases) if alias]


def _not_found(
    target_module: str,
    available_modules: list[str],
    error: str | None,
    target_granularity: str,
) -> dict:
    return {
        "found": False,
        "module": None,
        "available_modules": available_modules,
        "parent_arch_id": "UNKNOWN",
        "source_files": [],
        "target_granularity": target_granularity,
        "error": error or f"Module '{target_module}' was not found in the architecture input (不存在).",
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _try_load_yaml(content: str) -> Any:
    try:
        return yaml.safe_load(content)
    except Exception:
        return None


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if _is_table_separator(cells):
        return []
    return cells


def _is_table_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells if cell.strip())


def _has_bold(text: str) -> bool:
    return "**" in text


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_heading_title(text: str) -> str:
    text = _clean_markdown(text)
    text = re.sub(r"^\d+(?:\.\d+)*\s+", "", text)
    text = re.sub(r"^[\d.]+\s*", "", text)
    return text.strip(" -")


def _extract_possible_names(text: str) -> list[str]:
    cleaned = _clean_markdown(text)
    parts = re.split(r"[,/;]| and |、|，|；", cleaned)
    return [part.strip() for part in parts if _looks_like_module_name(part.strip())]


def _looks_like_module_name(name: str) -> bool:
    if not name or len(name) > 80:
        return False
    lowered = name.lower()
    if lowered in {"module", "bc", "bounded context", "source", "target", "component"}:
        return False
    return any(
        marker in name
        for marker in (
            "Core",
            "Agent",
            "Center",
            "Gateway",
            "Service",
            "Module",
            "Context",
            "PC ",
        )
    )


def _same_name(left: str, right: str) -> bool:
    return _normalize_name(left) == _normalize_name(right)


def _normalize_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _contains_any(text: str, aliases: list[str]) -> bool:
    normalized_text = _normalize_name(text)
    return any(alias and _normalize_name(alias) in normalized_text for alias in aliases)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if not item:
            continue
        key = _normalize_name(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe_modules(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for module in modules:
        key = (module.get("granularity"), _normalize_name(module.get("name", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(module)
    return result


def _dedupe_dicts_by_name(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = _normalize_name(str(item.get("name", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
