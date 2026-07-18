---
name: leaf-gate
description: Decide whether a recursively layered development node should continue layering, stop layering and enter code development, or return an evidence/contract error. Use after PRD-to-Architecture, PRD-to-Gherkin, and Mocktest have produced the current node's structured evidence.
---

# Leaf Gate

Evaluate one node only. Do not repair the PRD, architecture, testcases, or Mocktest; return `ERROR` so the orchestrator sends incomplete or invalid evidence back upstream.

## Formal JSON contract

Use structured mode whenever the node contains any of these inputs. A valid formal run requires all four:

```text
<node>/
  prd.json
  architecture.json
  testcases.json
  mocktest_report.json       # or leaf_gate_evidence.json
  leaf-gate.config.json      # optional
```

Every input must contain every shared field: `schema_version`, `run_id`, `project_id`, `node_id`, `parent_node_id`, `artifact_id`, `artifact_type`, `created_at`, `generator`, `status`, `input_artifacts`, and `requirement_ids`. The four identity fields must match; use `null` or `[]` only where a shared field is inapplicable. `prd.json` must additionally contain `depth`, `max_depth`, parent information, and an array `node_history`.

Require a passing Mocktest and full requirement-to-testcase coverage before deciding. Missing artifacts, invalid JSON, mismatched identities, failed/error Mocktest, or unverified requirements produce a formal `ERROR`; never default to `STOP_LAYERING`.

Run:

```bash
python scripts/run_leaf_gate.py <node-dir> --output <node-dir>/leaf_gate_decision.json
```

The script detects formal mode automatically. In formal mode it always writes these machine-consumable artifacts next to `--output` (or in `<node-dir>` if omitted):

- `leaf_gate_decision.json`
- `leaf_gate_metrics.json`
- `execution_log.json`
- `leaf_gate_annotation_template.json`

It also writes the human-readable `leaf_gate_decision.md`.

## Decisions and scheduling

Use only these formal decision/status values:

| Value | Meaning |
| --- | --- |
| `CONTINUE_LAYERING` | Configured complexity/risk evidence shows another independently implementable layer is useful. `proposed_children` is non-empty and scheduler-ready. |
| `STOP_LAYERING` | Responsibility is bounded, interfaces are clear, requirements are verified, architecture risks are acceptable, and Mocktest passed. Enter code development. |
| `ERROR` | Evidence or contract is not sufficient for a valid judgement, or depth is exhausted while decomposition is still required. Do not enter code development. |

Each proposed child includes `child_node_id`, `name`, `responsibility`, `requirement_ids`, `decomposition_rationale`, `expected_interfaces`, and `priority`.

At the lower of `prd.json.max_depth` and configured `max_recursion_depth`, return `ERROR` with `depth_limit_reached` and `manual_intervention_required` if a layering rule still triggers. Do not hide unresolved complexity behind `STOP_LAYERING`. A stop decision records separate evidence for single responsibility, interface clarity, verified requirements, acceptable architecture risk, and passing non-blocking Mocktest.

## Configuration and reproducibility

Configure thresholds under `thresholds` in `leaf-gate.config.json`; do not hard-code experiment settings. Supported formal thresholds are `max_requirements`, `max_components`, `max_interfaces`, `max_dependencies`, `max_architecture_depth`, `max_complexity`, `max_risks`, `max_recursion_depth`, `max_mock_defects`, `max_mock_critical_defects`, and `min_llm_confidence`.

The decision records metrics for requirements, components, interfaces, dependencies, architecture depth, complexity, risks, Mock defects, critical defects, uncovered requirements, unverified scenarios, and triggered rules. `execution_log.json` preserves input/output hashes and all standard experiment-log fields. Re-run the same structured inputs and configuration to compare `decision`, `triggered_rules`, `proposed_children`, `confidence`, and metrics.

For human-label comparison, give annotators `leaf_gate_decision.md` and `leaf_gate_annotation_template.json`. Valid labels are `CONTINUE_LAYERING`, `STOP_LAYERING`, and `CANNOT_JUDGE`, joined to system output by `node_id`.

## Legacy compatibility

The existing Markdown/Feature architecture-package mode remains supported for current users. It emits legacy `INPUT_ERROR` only as a compatibility transport status; adapt it to formal `ERROR` before producing a cross-module artifact. Legacy `LEAF_READY` or `DONE_LAYERING` inputs, if encountered upstream, must map to formal `STOP_LAYERING`; never emit them as new formal output.

Use the legacy LLM decomposition-gain flow only for non-structured packages. Its semantic result remains binary (`CONTINUE_LAYERING` or `STOP_LAYERING`); artifact incompleteness is not a semantic result.

## Resources

- `scripts/run_leaf_gate.py`: formal contract validation, metrics, decision, artifacts, plus legacy package discovery.
- `schemas/leaf_gate_decision.schema.json`: formal decision contract for downstream consumers.
- `references/leaf_gate_config.example.json`: complete configurable threshold set.
- `references/leaf_gate_rubric.md`: decomposition judgement criteria for legacy semantic evaluation.
- `references/llm_judge_prompt.md`: strict legacy semantic judge prompt.
