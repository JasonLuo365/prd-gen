"""Small YAML compatibility layer for PRD Flow.

PyYAML is preferred when installed. The fallback parser intentionally supports
only the subset used by PRD frontmatter and architecture fixtures: nested
mappings, lists, quoted strings, numbers, booleans, nulls, and inline lists.
"""

from __future__ import annotations

import json
from typing import Any

try:  # pragma: no cover - exercised only when PyYAML is installed.
    import yaml as _pyyaml
except ModuleNotFoundError:  # pragma: no cover - fallback is tested indirectly.
    _pyyaml = None


def safe_load(text: str) -> Any:
    """Load YAML with PyYAML when available, otherwise use a small fallback."""
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)

    stripped = text.strip()
    if not stripped:
        return None
    if stripped[0] in "[{":
        return json.loads(stripped)

    lines = _prepare_lines(text)
    if not lines:
        return None
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def dump(data: Any, allow_unicode: bool = True, sort_keys: bool = False) -> str:
    """Dump YAML with PyYAML when available, otherwise use a small fallback."""
    if _pyyaml is not None:
        return _pyyaml.dump(data, allow_unicode=allow_unicode, sort_keys=sort_keys)
    lines = _dump_value(data, indent=0, sort_keys=sort_keys)
    return "\n".join(lines) + "\n"


def _prepare_lines(text: str) -> list[tuple[int, str]]:
    prepared: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        prepared.append((indent, raw_line.strip()))
    return prepared


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    current_indent, content = lines[index]
    if current_indent < indent:
        return None, index
    if content.startswith("- "):
        return _parse_list(lines, index, current_indent)
    return _parse_mapping(lines, index, current_indent)


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            break
        if content.startswith("- "):
            break
        key, value = _split_key_value(content)
        if value == "":
            nested, index = _parse_block(lines, index + 1, indent + 2)
            result[key] = nested
        else:
            result[key] = _parse_scalar(value)
            index += 1
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent != indent or not content.startswith("- "):
            break
        item_text = content[2:].strip()
        index += 1

        if item_text == "":
            nested, index = _parse_block(lines, index, indent + 2)
            result.append(nested)
            continue

        if _looks_like_mapping_item(item_text):
            key, value = _split_key_value(item_text)
            item: dict[str, Any] = {}
            if value == "":
                nested, index = _parse_block(lines, index, indent + 2)
                item[key] = nested
            else:
                item[key] = _parse_scalar(value)

            while index < len(lines):
                next_indent, next_content = lines[index]
                if next_indent <= indent:
                    break
                if next_indent == indent + 2 and not next_content.startswith("- "):
                    nested_key, nested_value = _split_key_value(next_content)
                    if nested_value == "":
                        nested, index = _parse_block(lines, index + 1, indent + 4)
                        item[nested_key] = nested
                    else:
                        item[nested_key] = _parse_scalar(nested_value)
                        index += 1
                    continue
                break
            result.append(item)
            continue

        result.append(_parse_scalar(item_text))
    return result, index


def _split_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise ValueError(f"Unsupported YAML line: {text}")
    key, value = text.split(":", 1)
    return _strip_quotes(key.strip()), value.strip()


def _looks_like_mapping_item(text: str) -> bool:
    return ":" in text and not text.startswith(("http://", "https://"))


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in ("", "null", "Null", "NULL", "~"):
        return None
    if value in ("true", "True", "TRUE"):
        return True
    if value in ("false", "False", "FALSE"):
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if value.startswith("{") and value.endswith("}"):
        return json.loads(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return _strip_quotes(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _dump_value(data: Any, indent: int, sort_keys: bool) -> list[str]:
    prefix = " " * indent
    if isinstance(data, dict):
        keys = sorted(data) if sort_keys else data.keys()
        lines: list[str] = []
        for key in keys:
            value = data[key]
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_value(value, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}{key}: {_format_scalar(value)}")
        return lines
    if isinstance(data, list):
        if not data:
            return [f"{prefix}[]"]
        lines = []
        for item in data:
            if isinstance(item, dict):
                nested = _dump_value(item, indent + 2, sort_keys)
                if nested:
                    first = nested[0].lstrip()
                    lines.append(f"{prefix}- {first}")
                    lines.extend(nested[1:])
                else:
                    lines.append(f"{prefix}- {{}}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_dump_value(item, indent + 2, sort_keys))
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines
    return [f"{prefix}{_format_scalar(data)}"]


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list) and not value:
        return "[]"
    if isinstance(value, dict) and not value:
        return "{}"
    return json.dumps(str(value), ensure_ascii=False)
