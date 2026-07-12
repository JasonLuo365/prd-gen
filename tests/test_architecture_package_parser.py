"""Tests for Markdown architecture package parsing in Derive mode."""
from __future__ import annotations

import zipfile
from pathlib import Path

from prd_flow.derive.context_builder import build_derive_context
from prd_flow.derive.parser import extract_module_context


def _write_architecture_package(path: Path) -> None:
    path.mkdir()
    (path / "README.md").write_text("# Architecture Package\n", encoding="utf-8")
    (path / "01-system-overview.md").write_text(
        """# 01 - System Overview

## Bounded Contexts

| Bounded Context | Responsibility |
| --- | --- |
| **Task Management Center** | Owns task lifecycle and plan generation. |
| **Execution Center** | Orchestrates command execution and recovery. |
| **Authorization Center** | Owns grants and runtime access checks. |
| **PC Agent Edge** | Runs commands on the user's local PC. |
""",
        encoding="utf-8",
    )
    (path / "02-module-partitioning.md").write_text(
        """# 02 - Module Partitioning

## Module Overview

| Module | Included BC | Responsibility | Reason |
| --- | --- | --- | --- |
| **Cloud Core** | Task Management Center, Execution Center, Authorization Center | Cloud control plane. | Shared transaction boundary. |
| **PC Agent Edge** | PC Agent Edge | Local runtime. | Physical PC boundary. |
""",
        encoding="utf-8",
    )
    (path / "03-runtime-architecture.md").write_text(
        """# 03 - Runtime Architecture

Execution Center sends commands to PC Agent Edge and receives StepExecuted or StepFailed events.
""",
        encoding="utf-8",
    )
    (path / "05-data-model.md").write_text(
        """# 05 - Data Model

### Execution Center

| Aggregate | Responsibility |
| --- | --- |
| ExecutionSession | Runtime command and result state. |
""",
        encoding="utf-8",
    )
    (path / "06-interface-contracts.md").write_text(
        """# 06 - Interface Contracts

### 6.1.4 Execute Command

- Provider: Execution Center
- Consumer: PC Agent Edge
- Path: `POST /internal/executions/commands`
- **required_fields**: `session_id`, `command`
- **produced_fields**: `command_id`, `accepted_at`
- **error_codes**: `AGENT_OFFLINE`, `COMMAND_TIMEOUT`

### 6.1.5 Check Grants

- Provider: Authorization Center
- Consumer: Execution Center
- Path: `POST /internal/auth/grants/check`
- **required_fields**: `principal_id`, `grant_id`
- **produced_fields**: `allowed`, `expires_at`
- **error_codes**: `GRANT_EXPIRED`

### 6.1.6 External SMS Gateway ACL

- Provider: SMS Gateway
- Consumer: Execution Center
- Protocol: HTTPS
- Errors: `SMS_UNAVAILABLE`
""",
        encoding="utf-8",
    )


def test_extract_bounded_context_from_architecture_directory(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)

    result = extract_module_context(arch_dir, "Execution Center", target_granularity="bounded_context")

    assert result["found"] is True
    assert result["target_granularity"] == "bounded_context"
    assert result["module"]["name"] == "Execution Center"
    assert "Cloud Core" in result["available_modules"]
    assert "Execution Center" in result["available_modules"]
    assert {iface["name"] for iface in result["module"]["interfaces"]} == {
        "Execute Command",
        "Check Grants",
    }
    execute_command = next(iface for iface in result["module"]["interfaces"] if iface["name"] == "Execute Command")
    assert execute_command["path"] == "/internal/executions/commands"
    assert execute_command["request_fields"] == ["session_id", "command"]
    assert execute_command["response_fields"] == ["command_id", "accepted_at"]
    assert execute_command["error_codes"] == ["AGENT_OFFLINE", "COMMAND_TIMEOUT"]
    assert any(dep["name"] == "PC Agent Edge" for dep in result["module"]["dependencies"])


def test_extract_deployable_module_from_readme_path(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)

    result = extract_module_context(arch_dir / "README.md", "Cloud Core")

    assert result["found"] is True
    assert result["target_granularity"] == "deployable_module"
    assert result["module"]["name"] == "Cloud Core"
    assert result["module"]["included_contexts"] == [
        "Task Management Center",
        "Execution Center",
        "Authorization Center",
    ]


def test_extract_chinese_named_contract_and_skip_incomplete_external_acl(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    arch_dir.mkdir()
    (arch_dir / "README.md").write_text("# Architecture Package\n", encoding="utf-8")
    (arch_dir / "01-system-overview.md").write_text(
        """# 01 - System Overview

## Bounded Contexts

| Bounded Context | Responsibility |
| --- | --- |
| **User Identity BC** | Owns login and verification code state. |
""",
        encoding="utf-8",
    )
    (arch_dir / "02-module-partitioning.md").write_text(
        """# 02 - Module Partitioning

## Module Overview

| Module | Included BC | Responsibility | Reason |
| --- | --- | --- | --- |
| **Identity Module** | User Identity BC | Authentication boundary. | Owns identity lifecycle. |
""",
        encoding="utf-8",
    )
    (arch_dir / "06-interface-contracts.md").write_text(
        """# 06 - Interface Contracts

### 6.1 短信验证码发送

- 接口所有者: User Identity BC
- Path: `POST /api/v1/auth/otp/send`
- **输入**: `phoneNumber`
- **输出**: `requestId`, `sentAt`, `retryAfterSeconds`
- **错误码**: `429`, `400`, `502`

### 6.2 SMS Gateway ACL

- Provider: SMS Gateway
- Consumer: User Identity BC
- Protocol: HTTPS
""",
        encoding="utf-8",
    )

    result = extract_module_context(arch_dir, "Identity Module", target_granularity="deployable_module")

    assert result["found"] is True
    assert [iface["name"] for iface in result["module"]["interfaces"]] == ["短信验证码发送"]
    contract = result["module"]["interfaces"][0]
    assert contract["method"] == "POST"
    assert contract["path"] == "/api/v1/auth/otp/send"
    assert contract["request_fields"] == ["phoneNumber"]
    assert contract["response_fields"] == ["requestId", "sentAt", "retryAfterSeconds"]
    assert contract["error_codes"] == ["429", "400", "502"]


def test_extract_component_from_nested_architecture_output(tmp_path: Path) -> None:
    arch_output = tmp_path / "architecture" / "output"
    arch_output.mkdir(parents=True)
    (arch_output / "02-module-partitioning.md").write_text(
        """# 02 Module Partitioning

## Component Partitioning

| Component | Responsibility | Related Aggregate |
|---|---|---|
| Consent Component | 隐私提示展示、学生确认、同意记录管理 | PrivacyConsent |
| Image Validation Component | 格式校验、大小校验、损坏检测 | ImageSubmission |
""",
        encoding="utf-8",
    )

    result = extract_module_context(tmp_path / "architecture", "Consent Component", target_granularity="component")

    assert result["found"] is True
    assert result["target_granularity"] == "component"
    assert result["module"]["name"] == "Consent Component"
    assert result["module"]["responsibility"] == "隐私提示展示、学生确认、同意记录管理"
    assert "Image Validation Component" in result["available_modules"]
    assert "Component" not in result["available_modules"]


def test_component_catalog_assigns_nested_api_and_data_migration_owner(tmp_path: Path) -> None:
    arch_output = tmp_path / "architecture" / "output"
    arch_output.mkdir(parents=True)
    (arch_output / "02-module-partitioning.md").write_text(
        """| Component | Responsibility | Related Aggregate |
|---|---|---|
| Image Submission Component | 图片集提交、数量限制、对象存储写入 | ImageSubmission |
| Image Validation Component | 格式校验、大小校验、损坏检测 | ImageSubmission |
""",
        encoding="utf-8",
    )
    (arch_output / "05-data-model.md").write_text(
        """## Aggregate Roots

| Aggregate Root | Responsibility | Stored In |
|---|---|---|
| ImageSubmission | 图片集提交与校验 | PostgreSQL |
""",
        encoding="utf-8",
    )
    (arch_output / "06-interface-contracts.md").write_text(
        """## REST API Summary

| Method | Path | Contract ID | Purpose |
|---|---|---|---|
| POST | `/api/v1/problems/images` | PI-API-003 | 上传题目图片 |

## PI-API-003: Upload Problem Images

### Request
```typescript
type UploadRequest = { images: string[]; };
```

### Success Response (200)
```typescript
type UploadResponse = { image_upload_id: string; status: string; };
```

### Failure Response (422)
```typescript
type Failure = { code: "too_many_images" | "invalid_image_format"; };
```

### Event Contract Index
| contract_id | contract_type | Event Name | Publisher | Consumers | required_fields | produced_fields | side_effects | dependencies |
|---|---|---|---|---|---|---|---|---|
| `EVT-IMG-001` | `event` | `ImagesSubmitted` | Image Submission Component | Image Validation Component | `event_id`, `image_ids` | `image_ids` | Starts validation. | Event Bus |

### Metric Contract Index
| metric_id | Owner | Source Events / Logs | Start | End | Threshold | Exclusions | Evidence |
|---|---|---|---|---|---|---|---|
| `MET-IMG-P95` | Image Submission Component | upload logs | upload submitted | upload accepted | P95 <= 2s | invalid requests | histogram |
""",
        encoding="utf-8",
    )

    result = extract_module_context(
        tmp_path / "architecture",
        "Image Submission Component",
        target_granularity="component",
    )

    assert [asset["name"] for asset in result["module"]["data_assets"]] == ["ImageSubmission"]
    assert [interface["path"] for interface in result["module"]["interfaces"]] == [
        "/api/v1/problems/images"
    ]
    assert [event["event_name"] for event in result["module"]["events"]] == ["ImagesSubmitted"]
    assert [metric["metric_id"] for metric in result["module"]["metric_contracts"]] == [
        "MET-IMG-P95"
    ]
    assert result["architecture_coverage_gaps"] == []


def test_extract_from_zipped_architecture_package(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)
    zip_path = tmp_path / "architecture.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file in arch_dir.iterdir():
            archive.write(file, arcname=f"architecture/{file.name}")

    result = extract_module_context(zip_path, "PC Agent Edge", target_granularity="deployable_module")

    assert result["found"] is True
    assert result["module"]["name"] == "PC Agent Edge"
    assert "06-interface-contracts.md" in result["source_files"]


def test_build_context_uses_architecture_package_for_requirement_matching(tmp_path: Path) -> None:
    arch_dir = tmp_path / "architecture"
    _write_architecture_package(arch_dir)
    parent_prd = tmp_path / "parent_prd.md"
    parent_prd.write_text(
        """---
doc_id: "ROOT-PRD-v1.0"
---

# Requirements

- [REQ-001] Execution Center shall execute commands through PC Agent Edge.
- [REQ-002] Authorization Center shall reject expired grants.
""",
        encoding="utf-8",
    )

    context = build_derive_context(parent_prd, arch_dir, "Execution Center", target_granularity="bounded_context")

    assert context["success"] is True
    assert context["parent_doc_id"] == "ROOT-PRD-v1.0"
    assert context["module_name"] == "Execution Center"
    assert [req["id"] for req in context["related_requirements"]] == ["REQ-001", "REQ-002"]
