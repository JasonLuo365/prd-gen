---
name: prd-generation
description: Use when the user explicitly asks to generate, write, create, or derive a PRD; invokes PRD Generation, Root mode, or Derive mode; or provides parent_prd, architecture_package or parent_architecture, and target_module for lower-level PRD generation.
---

# PRD Generation

## Purpose and Boundary

Generate one Markdown PRD or one complete layer of child PRDs as evidence-preserving inputs to the downstream test-generation skill.

This skill owns:

- product scope, atomic requirements, and stable IDs;
- business behavior and observable pass/fail oracles;
- NFR measurement definitions;
- traceability, exclusions, and oracle-readiness review.

This skill does **not** generate test cases or Gherkin. The downstream test skill owns Requirement Model, test design, TC, and mechanical Gherkin rendering. Never add `Feature`, `Scenario`, `Given`, `When`, `Then`, `gherkin_count`, or fabricated “basic scenarios” to this PRD.

Before running either mode, read [references/prd-to-gherkin-handoff-contract.md](references/prd-to-gherkin-handoff-contract.md) completely. It is the normative field schema and gate definition.

## Trigger and Mode

Trigger only when the user clearly asks to create or derive a PRD. Discussion or review of the Skill alone does not trigger generation.

Choose one mode:

| Input | Mode |
|---|---|
| New/top-level product or feature | Root |
| `parent_prd` + architecture input + `target_module` | Derive |
| Ambiguous “write a PRD” | Ask whether top-level or derived |

Root is a one-question-at-a-time elicitation workflow. Derive is deterministic and must preserve parent evidence; do not ask content questions unless source evidence is genuinely missing and the user explicitly wants to resolve it.

Root is also a resumable state machine. Producing Markdown is not completion. The workflow remains in elicitation until every current-release blocker is either answered with authorized evidence or removed from the release by an explicit product-owner scope decision.

## Evidence Policy

Classify every normative statement internally:

- `EXPLICIT`: stated by the user or source document.
- `VALID_DERIVATION`: mechanically entailed by explicit parent/architecture contracts, with evidence references.
- `ASSUMPTION`: plausible but not authorized.
- `UNKNOWN`: no defensible answer.

Only `EXPLICIT` and `VALID_DERIVATION` may become current-release requirements or Acceptance Contracts. An assumption may be proposed as a question, never silently promoted. An unknown business response, threshold, exception, boundary, or exclusion is a blocker.

## Root Workflow

Ask one choice-first question at a time. Offer 2–4 mutually exclusive directions, mark a recommended default when useful, and allow free-form supplementation. Summarize each material decision before proceeding.

### R1. Identify Product and Release Boundary

Capture product, users, problem, desired outcome, platform/domain boundary, current release, non-goals, dependencies, and data availability.

For every candidate clause choose:

- `current`: normative in this release;
- `out_of_version`: real but planned later;
- `not_applicable`: explicitly excluded.

Require `scope_reason` for non-current items. Never use “future” to hide a missing current-release oracle.

### R1A. Freeze Scope Commitments

Before writing Acceptance Contracts, obtain an explicit release-scope decision for every candidate clause. This is mandatory for `Should` and `Could` clauses: priority is not permission to leave their release status ambiguous.

For each candidate, record one of `current`, `out_of_version`, or `not_applicable` plus its decision evidence. If the user keeps a clause `current`, all of its business responses and verification fields must be resolved. If the user moves it out of the release, record the reason; do not continue asking for its current-release oracle.

### R2. Build the Problem Model

Capture target users, jobs, pain points, current alternatives, value proposition, constraints, risks, and success hypotheses. Separate facts from proposed choices.

### R3. Elicit and Atomize Requirements

Give each requirement one stable ID. Use `REQ-###` for functional clauses and `NFR-###` for non-functional clauses.

Each current-release requirement must express one independently verifiable obligation. Split clauses joined by “and/同时/以及” when they can pass or fail independently. A heading or capability summary may remain descriptive, but mark it `requirement_kind: aggregate` and give its normative children separate atomic IDs. Current normative clauses must be `requirement_kind: atomic`.

Capture MoSCoW priority for planning only. Priority never changes oracle obligations: every current `Must`, `Should`, and `Could` clause needs complete coverage.

### R4. Define Success Metrics and NFR Measurement

Define product success metrics with stable IDs, target, measurement method, and linked NFR/outcome IDs.

For every current NFR, capture a complete NFR Verification Contract:

- population/sample;
- measurement start and end;
- unit;
- threshold;
- exclusions;
- pass rule;
- evidence references.

Do not accept “fast”, “stable”, “high accuracy”, a percentile, or a threshold alone. A numeric target without population, interval, exclusions, and pass rule remains blocked.

First classify each quality obligation:

- `deterministic_invariant`: every applicable event or record must obey a rule. Model this as an atomic functional/governance clause with a functional Acceptance Contract and explicit failure response.
- `statistical_nfr`: compliance is decided over a measured population or window. Keep it as an NFR and require the complete NFR Verification Contract above.

Do not force deterministic invariants into artificial sampling contracts, and do not disguise statistical targets as deterministic rules to avoid defining measurement.

### R5. Define Functional Acceptance Contracts

For every current functional atomic requirement, capture one or more Acceptance Contracts with:

- contract ID and `verifies` requirement IDs;
- actor;
- preconditions;
- trigger;
- required system response;
- observable pass/fail oracles;
- boundary condition **and its required response**;
- exception condition **and its required response**;
- evidence references.

Write business rules, not testing syntax. A boundary value without the corresponding response is incomplete. “Returns expected result”, “works normally”, or “handles error” is not an oracle.

### R6. Reconcile Scope and Traceability

Build the Oracle Coverage Ledger. Every requirement must resolve to exactly one status:

- `ready`: current and linked to at least one complete, type-compatible contract;
- `blocked`: current but missing/invalid oracle evidence;
- `excluded`: explicitly non-current with a reason.

Resolve duplicate IDs, unknown references, conflicting responses, orphan contracts, mixed release scopes, and aggregate normative clauses.

### R6A. Oracle Closure Loop

After each reconciliation, execute this loop until the blocked count is zero:

1. Recompute the Oracle Coverage Ledger and list exact missing fields by requirement ID.
2. Resolve scope blockers first, then functional-oracle blockers, then NFR measurement blockers.
3. Ask exactly one choice-first question at a time. Recommend an option when evidence supports it, but never select it for the user.
4. Record the answer as a product decision or fact with a stable evidence reference.
5. Update the affected requirement, contract, exclusions, decisions, and ledger.
6. Re-run all mechanical gates before asking the next question.

Do not declare the PRD complete, recommend test generation, or invoke a downstream test workflow while this loop has blockers. If the user explicitly stops before closure, preserve the work as a draft and list the next unresolved question.

### R7. Agent Review and Release Gate

Run an independent Agent review against the handoff contract only after the Oracle Closure Loop reaches zero blockers. Review the artifact, not the author’s notes. Report every issue by requirement/contract ID and field. Treat every review finding as a new blocker and return to R6A; re-run independent review after corrections.

The PRD may be marked `ready_for_test_generation: true` only when:

- release scope is frozen;
- all current functional and NFR clauses are atomic;
- all current clauses have complete explicit oracles;
- coverage ledger has zero `blocked` rows;
- there are no unknown references or unresolved conflicts;
- the independent Agent review passes.

If blocked, output a draft plus a Blocking Questions table. Do not weaken or auto-fill the gate.

### R8. Resume from a Downstream Quality Report

When a downstream quality report blocks an existing PRD, do not restart Root elicitation:

1. Parse each blocked item, missing field, requirement ID, and decision ID from the report.
2. Map it to the source requirement, Acceptance Contract, NFR contract, or release-scope decision.
3. Preserve valid existing content and ask only for missing authorized decisions, using R6A one question at a time.
4. Update the PRD in place as a new version, recompute the ledger, and run the full release gate.
5. A downstream report saying “partial”, “blocked”, or “needs review” can never be converted to ready by changing metadata alone.

## Executable Entrypoints

Run the bundled launcher from a clean extracted package; do not ask callers to set `PYTHONPATH`:

```powershell
python skills/prd-generation/scripts/run_prd_flow.py --help
```

For reproducible Root experiments, provide a UTF-8 JSON/YAML input with `P1`…`P6` (or the documented phase aliases), explicit evidence, requirements, contracts, and metrics. Provide identity/model fields on the command line and an independently produced review artifact. `--validate-only` writes only the blocked draft/sidecars and never calls `input()`.

```powershell
python skills/prd-generation/scripts/run_prd_flow.py `
  --input <root-input.json> --output-dir <output-dir> `
  --run-id <run-id> --project-id <project-id> --node-id <node-id> `
  --model <model> --model-params <json> --seed <seed> `
  --review-artifact <review.json>
```

The review artifact must be a separate execution and contain the canonical `input_hash`, reviewer/model, timestamp, findings, and `status: passed`. A caller-supplied `agent_review_passed` boolean is never review evidence. Every Root run writes `prd.json`, `prd_manifest.json`, `validation_report.json`, and `execution_log.json` from the same in-memory model; blocked runs also write `blocking_questions.json`.

Use exit codes consistently: `0` handoff-ready success; `2` quality/oracle/scope/inheritance/review block; `3` dependency/configuration/environment error; `4` unhandled runtime error; `5` schema/contract incompatibility. Input errors use `1` and must not be reported as success.

## Derive Workflow

Use the bundled backend:

```powershell
python skills/prd-generation/scripts/run_prd_flow.py `
  --parent-prd <path> `
  --architecture-package <path> `
  --target-module <name> `
  --target-granularity <auto|deployable_module|bounded_context|component> `
  --output-dir <product-output-root>
```

Use explicit `--output <path>` instead when a single derived PRD must be written to a caller-selected file rather than the inferred layered structure.

To derive every direct child declared by one architecture layer, use the full-layer command:

```powershell
python skills/prd-generation/scripts/run_prd_flow.py `
  --derive-all `
  --parent-prd <path> `
  --architecture-package <path> `
  --target-granularity <deployable_module|bounded_context|component> `
  --output-dir <product-output-root>
```

Full-layer Derive writes only one child PRD per direct architecture child by default. `--output-dir` is the product output root, not the final layer directory. When the parent PRD path contains a layer-qualified directory such as `L0-root` or `L1-profile-intelligence`, Derive infers the next layer and writes `L1/L1-<child>/prd.md` for L0 children, or `L<n>/<parent-abbreviation>/L<n>-<parent-abbreviation>-<child>/prd.md` for deeper layers. It removes a shared child namespace that repeats the parent identity, such as `cfg-*`, `PI-*`, or `L1-PL-*`. If the parent layer cannot be inferred, preserve the legacy flat `L1-<child>/prd.md` behavior. Keep the allocation ledger in memory as a pre-generation correctness gate. For explicit diagnostics only, add `--allocation-report <path>` to write the ledger as JSON; this report is not a PRD deliverable or Leaf Gate evidence. Do not generate a layer index file.

Legacy `--parent-architecture` may replace `--architecture-package`.

Architecture inputs may be either a top-level system package or a recursive child package. Recursive packages may use `architecture-manifest.yaml`, `02-architecture-decomposition.md`, `03-state-and-data.md`, `04-contracts-and-runtime.md`, optional `00-machine-readable-contracts.md`, and `child-handoff.md`. Their `child_id` / next-layer `target_node_id` rows are direct children at `component` granularity even when the IDs do not end in `Component`. Compact allocations such as `D001-D003`, `REQ-D004/D006`, and `NFR-D001~003` map to current-layer IDs.

When one parent Acceptance Contract spans requirements owned by different direct children, the architecture package must include `acceptance-contract-projections.yaml`. Each record identifies `target_module`, `parent_contract`, and either `mode: shared` (the complete parent behavior is intentionally shared integration context) or `mode: project` with a complete child-scoped contract. The backend treats this as declarative input; it must never read an existing child PRD as a hidden override. Missing or invalid projection data blocks the whole layer atomically.

Derive rules:

1. Use architecture only to enumerate direct child modules and determine ownership. Do not turn architecture descriptions into new product requirements.
2. Allocate every current, in-scope parent functional clause, NFR, Acceptance Contract, and success metric to at least one direct child. Preserve future backlog and architecture-explicit out-of-scope/delegated items as exclusions without forcing a false child owner. Allow intentional multi-owner allocation.
3. Generate exactly one `prd.md` per direct child. Preserve parent semantics, scope, priority, contracts, metrics, exclusions, and evidence; record the parent ID on every inherited requirement.
4. Require the union of all child assignments to cover every parent item with no unknown IDs and no unassigned items. Fail without changing existing outputs if coverage is incomplete.
5. Do not run SMART rewriting, independent Agent review, complexity budgets, layer-depth rules, leaf-candidate logic, test generation, architecture validation, or Mock validation in Derive.
6. Do not generate drafts, indexes, allocation reports, or error files by default. `--allocation-report <path>` is an explicit diagnostic option only.
7. Leave testcase generation, architecture generation, testcase-driven Mock validation, and Leaf Gate to their downstream stages.
8. Require every generated direct child to contain at least one inherited current-release obligation. Require every inherited current requirement to retain a complete compatible parent Acceptance Contract, and require every inherited metric requirement reference to resolve to a child requirement ID. Any failure blocks the whole layer atomically and leaves existing outputs unchanged.
9. Never special-case a product or module in code. Resolve split parent contracts only through the generic `acceptance-contract-projections.yaml` schema.
10. Treat explicit direct-child requirement allocations as authoritative owners. A support, dependency, consumer, or input-precondition reference is not ownership. Semantic matching may fill only requirements with no explicit owner, and an Acceptance Contract projection must never expand requirement ownership.

Never create a success response, error response, boundary, threshold, or exclusion in Derive. Preserve only the corresponding parent content. Do not generate a placeholder scenario.

## Output Contract

Produce sections in this order:

1. YAML frontmatter
2. Problem Statement
3. Scope and Non-goals
4. Current Release — Functional Requirements
5. Current Release — Non-functional Requirements
6. 架构输入契约
7. Success Metrics
8. Acceptance Contracts
9. Oracle Coverage Ledger
10. Future Backlog / Documented Exclusions
11. Risks, Dependencies, and Blocking Questions
12. Agent Review Report (Root mode only)

## 架构输入契约

当 PRD 将被架构生成 Skill 使用时，加入“架构输入契约”章节。该章节应与规范性产品需求分开，仅记录明确的系统边界、外部依赖、数据与存储约束、运行时/容量约束、安全/隐私约束、部署约束，以及需要人工确认的架构决策。不得擅自指定数据库、队列、云厂商、框架、模型托管方式或部署拓扑。未决的架构选择必须标记为待确认决策，不得默默升级为产品需求。

Root frontmatter must include:

```yaml
doc_type: prd
schema_version: "2.0"
release_scope_frozen: true
ready_for_test_generation: true
oracle_blocked_count: 0
review_method: independent_agent
```

Also preserve the shared identity fields without renaming them: `run_id`, `project_id`, `node_id`, `parent_node_id`, `artifact_id`, `artifact_type`, `created_at`, `generator`, `status`, `input_artifacts`, and `requirement_ids`. The manifest carries all of them; include the applicable PRD/handoff fields in frontmatter.

Set readiness fields to false/nonzero for a draft. Never claim readiness merely because the Markdown was produced.

Derive frontmatter must include `status: complete`, `inheritance_complete: true`, `ready_for_test_generation: true`, and `review_method: inheritance_allocation_gate`. It must not require `agent_review_passed`.

Keep Derive frontmatter compact. Record architecture links only as ordered, deduplicated identifier lists named `interface_refs`, `dependency_refs`, and `event_refs`. Do not copy complete interface, dependency, or event objects into PRD frontmatter. Full architecture records remain authoritative in the architecture package and may still be used internally while deriving the PRD body.

### Terminal States and Handoff Gate

Root has exactly two valid terminal artifact states:

| State | Filename | Required metadata | Downstream handoff |
|---|---|---|---|
| Draft completed | `*.draft.md` | `status: draft`, `ready_for_test_generation: false`, nonzero `oracle_blocked_count` or pending/failed review | prohibited |
| Ready for test generation | `*.md` | `status: approved`, `release_scope_frozen: true`, `ready_for_test_generation: true`, `oracle_blocked_count: 0`, `agent_review_passed: true` | allowed |

The handoff gate is hard: do not recommend or run downstream test generation unless every ready-state field is satisfied. A syntactically complete document with unresolved business choices is still a draft. Renaming a draft or changing frontmatter does not satisfy the gate.

Derive has one successful artifact state: `prd.md` with complete inheritance metadata. On invalid input or incomplete allocation, return an error and write no child PRD. Independent review is not a Derive terminal condition.

## Red Flags

Stop and resolve or block when any occurs:

- Gherkin or test-case syntax appears in generated Acceptance content;
- only Must requirements are covered;
- `gherkin_count` is used as evidence;
- the Agent invents a `Then`-equivalent response;
- NFR has a number but no full measurement contract;
- exception/boundary names exist without required responses;
- current behavior is moved to backlog only because its oracle is unknown;
- Derive mode generates generic “success”, “normal operation”, or “expected result” behavior;
- Root review is performed by the same generation pass without an independent review pass.

## Validation

After modifying the backend or templates, run:

```powershell
pytest -q
python C:/Users/Lenovo1/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/prd-generation
```

Also compare the workspace and bundled `prd_flow` copies. They must be identical before delivery.
