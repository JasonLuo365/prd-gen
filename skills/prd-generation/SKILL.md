---
name: prd-generation
description: Use when the user explicitly asks to generate, write, create, or derive a PRD; invokes PRD Generation, Root mode, or Derive mode; or provides parent_prd, architecture_package or parent_architecture, and target_module for lower-level PRD generation.
---

# PRD Generation

## Purpose and Boundary

Generate one Markdown PRD that is a complete, evidence-preserving input to the downstream test-generation skill.

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

## Derive Workflow

Use the bundled backend:

```powershell
python skills/prd-generation/scripts/prd_flow/main.py `
  --parent-prd <path> `
  --architecture-package <path> `
  --target-module <name> `
  --target-granularity <auto|deployable_module|bounded_context|component> `
  --output <path>
```

Legacy `--parent-architecture` may replace `--architecture-package`.

Derive rules:

1. Parse atomic requirements, release scopes, Acceptance Contracts, NFR contracts, metrics, and evidence references from the parent PRD.
2. Map only relevant clauses to the target architecture owner.
3. Preserve parent semantics and MoSCoW priority. Child IDs reference parent IDs.
4. A new child contract is allowed only when an explicit interface/event/data/metric contract entails the response and the evidence reference is recorded.
5. Never create a success response, error response, boundary, threshold, or exclusion from generic architecture knowledge.
6. If a current child clause has no complete oracle, block the derived PRD. Do not generate a placeholder scenario.
7. Run the same Oracle Coverage Ledger and independent Agent review as Root mode.

## Output Contract

Produce sections in this order:

1. YAML frontmatter
2. Problem Statement
3. Scope and Non-goals
4. Current Release — Functional Requirements
5. Current Release — Non-functional Requirements
6. Success Metrics
7. Acceptance Contracts
8. Oracle Coverage Ledger
9. Future Backlog / Documented Exclusions
10. Risks, Dependencies, and Blocking Questions
11. Agent Review Report

Frontmatter must include:

```yaml
doc_type: prd
schema_version: "2.0"
release_scope_frozen: true
ready_for_test_generation: true
oracle_blocked_count: 0
review_method: independent_agent
```

Set readiness fields to false/nonzero for a draft. Never claim readiness merely because the Markdown was produced.

### Terminal States and Handoff Gate

Root and Derive have exactly two valid terminal artifact states:

| State | Filename | Required metadata | Downstream handoff |
|---|---|---|---|
| Draft completed | `*.draft.md` | `status: draft`, `ready_for_test_generation: false`, nonzero `oracle_blocked_count` or pending/failed review | prohibited |
| Ready for test generation | `*.md` | `status: approved`, `release_scope_frozen: true`, `ready_for_test_generation: true`, `oracle_blocked_count: 0`, `agent_review_passed: true` | allowed |

The handoff gate is hard: do not recommend or run downstream test generation unless every ready-state field is satisfied. A syntactically complete document with unresolved business choices is still a draft. Renaming a draft or changing frontmatter does not satisfy the gate.

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
- review is performed by the same generation pass without an independent review pass.

## Validation

After modifying the backend or templates, run:

```powershell
pytest -q
python C:/Users/Lenovo1/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/prd-generation
```

Also compare the workspace and bundled `prd_flow` copies. They must be identical before delivery.
