---
name: leaf-gate
description: Use when deciding only whether a validated layered PRD node should continue layering or stop layering and enter implementation.
---

# Leaf Gate

## Purpose

Leaf Gate is a binary stopping decision in an explainable layered development flow. It answers one question:

> Will another layer materially reduce behavior complexity, boundary width, implementation context, verification coupling, or residual risk?

It does not repair the PRD, testcase, or architecture. Architecture correction belongs to the upstream testcase-driven mock/validation loop. Run Leaf Gate only after that loop has produced an effective architecture package for the current node.

The only final decisions are:

| Decision | Meaning |
| --- | --- |
| `CONTINUE_LAYERING` | Create lower-layer nodes because another layer has material value. |
| `STOP_LAYERING` | Further layering has no material value; the node may enter implementation. |

`INPUT_ERROR` is a tool execution status, not a third Leaf Gate decision. It means the upstream artifacts are not ready for a layering judgement.

## Input Contract

A node normally contains:

```text
node-id/
  prd.md
  testcase.feature
  architecture.md|yaml|json
  traceability.md              # may be generated/refreshed by Leaf Gate
  risks.md                     # may be generated/refreshed by Leaf Gate
```

Multi-file architecture packages are supported. This flattened example is not a fixed template:

```text
node-id/
  prd.md
  testcase.feature
  architecture/
    README.md                  # optional package index/manifest
    <effective architecture documents...>
```

Recursive architecture packages are also valid. An `architecture-manifest.yaml` artifact inventory may select files such as `02-architecture-decomposition.md`, `03-state-and-data.md`, `04-contracts-and-runtime.md`, optional machine-readable contracts, and `child-handoff.md`.

Nested packages are also supported:

```text
node-id/
  architecture/
    <package directory>/
      README.md
      <effective architecture documents...>
    <optional validation or provenance documents...>
```

Leaf Gate does not require a validation report file. The stable prerequisite is that the architecture package has already passed the upstream testcase-driven mock/validation loop. That process may be folded into the final package and leave no separate report.

## Architecture Package Discovery

Do not assume a fixed directory, file count, numbering scheme, language, or contract filename.

Discovery order:

1. Explicit `--architecture` file or architecture root.
2. Conventional single architecture file.
3. Architecture package directory.
4. Matched architecture file as a fallback.

Inside a directory, prefer local links declared by README/index/manifest/目录/索引/清单. Without a usable manifest, select the directory with the strongest semantic coverage of system context, runtime, data/consistency, contracts, decisions, and deployment.

Files are classified by role:

| Role | Meaning | Layering evidence use |
| --- | --- | --- |
| `primary` | Effective architecture package used by downstream implementation. | Authoritative. |
| `validation` | Optional validation/review/acceptance reports. | Risk and provenance only; never replaces primary evidence. |
| `remediation` | Optional modification or remediation plans. | Intent only; never proves a completed change. |
| `supporting` | Workbench, generation plan, assumptions, DDD analysis, and other source material. | Non-authoritative unless promoted by the package manifest. |

The static report exposes `architecture_files`, `architecture_validation_files`, `architecture_remediation_files`, `architecture_supporting_files`, `architecture_manifest`, and `architecture_selection`. Inspect the inventory before semantic judgement. If classification is wrong, correct the explicit input mapping and rerun.

## Preconditions Versus Decisions

Leaf Gate must not translate artifact-quality problems into layering decisions.

The following are precondition failures:

- missing PRD, testcase, architecture, traceability, or risks;
- missing contract inputs, outputs, errors, states, side effects, or dependencies;
- unmapped current-layer requirements;
- untagged scenarios;
- weak or missing primary-architecture evidence;
- unresolved high risks;
- unresolved TODO/TBD or open questions;
- invalid, incomplete, low-confidence, or non-binary semantic judgement.

Return an error object without `decision`:

```json
{
  "status": "INPUT_ERROR",
  "error": "UPSTREAM_VALIDATION_INCOMPLETE",
  "message": "The upstream artifacts are not ready for a layering decision.",
  "details": {}
}
```

Do not generate refinement routes. Send the error back to the existing upstream validation workflow using the normal workflow orchestration outside Leaf Gate.

## Workflow

1. Confirm the current node has completed testcase-driven architecture mock/validation.
2. Discover the PRD, current-node testcase, effective architecture package, and optional provenance files.
3. Prepare or refresh `traceability.md` and `risks.md`.
4. Run deterministic checks.
5. Stop with `INPUT_ERROR` if a precondition is incomplete.
6. If deterministic complexity already proves another layer is useful, return `CONTINUE_LAYERING`.
7. Otherwise run the LLM semantic decomposition-gain judgement.
8. Return exactly `CONTINUE_LAYERING` or `STOP_LAYERING`.

Static evidence can be generated before LLM judgement:

```bash
python scripts/run_leaf_gate.py <node-dir> \
  --architecture architecture \
  --output <node-dir>/leaf-gate.static.json
```

When static evidence is valid but not conclusive, the report has `phase: STATIC_EVIDENCE` and `decision: null`. This is an unfinished evaluation phase, not a Leaf Gate result. Supply semantic judgement to produce a final binary result:

```bash
python scripts/run_leaf_gate.py <node-dir> \
  --architecture architecture \
  --llm-judgement <node-dir>/leaf-gate.llm.json \
  --output <node-dir>/leaf-gate.report.json
```

Use explicit `--prd`, `--feature`, `--architecture`, `--traceability`, `--risks`, `--config`, and `--profile` paths for unusual layouts.

## Five Criteria

### C1 Behavior Complexity

Determine whether the testcase contains multiple independent behavior families, business loops, subsystems, or an oversized Scenario/Outline. Materially separable behavior means `CONTINUE_LAYERING`.

### C2 Boundary Width

Contract-field completeness is a prerequisite. Once complete, judge whether the node still crosses multiple independently implementable contracts, ownership boundaries, or consistency boundaries. A broad semantic boundary means `CONTINUE_LAYERING`.

### C3 Implementation Context

Determine whether one implementation session can hold the required PRD, testcase, contracts, runtime/data constraints, and risk evidence. Excess context caused by separable responsibilities means `CONTINUE_LAYERING`.

### C4 Independent Verifiability

Trace completeness is a prerequisite. Once complete, judge whether the node can be implemented and automatically verified as one independent unit, or whether tests couple several separable child behaviors. Material verification coupling means `CONTINUE_LAYERING`.

### C5 Decomposition Gain

Judge the marginal value of another layer. Continue only when child nodes would materially improve responsibility clarity, context control, test isolation, risk isolation, or parallel implementation. Stop when children would be pass-through wrappers, mechanical layers, or arbitrary document splits.

## Evidence Preparation

Generated traceability uses these strengths:

| Strength | Meaning | Effect |
| --- | --- | --- |
| `strong` | Direct requirement ID, an equivalent compact derived allocation (`D001-D003` → `REQ-D001`…`REQ-D003`), or strong contract/boundary evidence. | Prerequisite satisfied. |
| `medium` | Multiple explicit architecture/profile identifiers. | Prerequisite satisfied. |
| `weak` | Broad lexical overlap only. | `INPUT_ERROR`; upstream validation is incomplete. |
| `none` | No usable primary-architecture evidence. | `INPUT_ERROR`; upstream validation is incomplete. |

For derived PRDs, current-layer IDs such as `REQ-D001`, `NFR-D001`, and `REQ-IF001` are the requirements that must map to testcase and architecture evidence. Parent IDs are traceability metadata, not replacement testcase tags.

`traceability.md` and `risks.md` are evidence indexes, not self-certifying proof. Semantic judgement must cite the underlying PRD, testcase, primary architecture, and static report.

## Output

A final report contains:

- `phase: FINAL`;
- one of the two decisions;
- evidence-backed five-criterion judgement;
- `next_action.type: decompose|vibecode`;
- optional child-cut suggestions for `CONTINUE_LAYERING`.

When `CONTINUE_LAYERING` is returned, the script may write `leaf-gate.decomposition.md`. Leaf Gate does not write refinement indexes, owner routes, or target-specific correction files.

## Hard Rules

- Never emit a third final decision.
- Never use `CONTINUE_LAYERING` as a synonym for incomplete artifacts.
- Never use `STOP_LAYERING` from static evidence alone unless the semantic judgement is present.
- Never repair or invent missing architecture/testcase content inside Leaf Gate.
- Never let validation, remediation, or supporting files replace primary architecture evidence.
- Every semantic pass or fail must cite artifact-backed evidence.
- A failed semantic criterion means another layer has material value, not that an upstream artifact needs refinement.
- Recommend children by behavior, ownership, contract, consistency, or risk boundary; never by arbitrary document sections.

## Resources

- `scripts/run_leaf_gate.py`: artifact discovery, evidence preparation, deterministic checks, input validation, and binary decision combination.
- `references/leaf_gate_rubric.md`: full decomposition-focused criteria.
- `references/llm_judge_prompt.md`: strict binary semantic judgement prompt.
- `references/report_template.json`: final report shape.
- `references/pressure_scenarios.md`: workflow pressure scenarios.
