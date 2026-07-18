# PRD Generation

Install the dependencies in `scripts/requirements.txt`, then use the portable Windows-safe entry point:

```powershell
python scripts/run_prd_flow.py --help
```

Do not set `PYTHONPATH`. All input and output text is UTF-8.

## Root

Interactive Root asks one question at a time:

```powershell
python scripts/run_prd_flow.py
```

For experiments, pass a UTF-8 JSON/YAML model and a separately produced review artifact:

```powershell
python scripts/run_prd_flow.py --input root.json --output-dir artifacts/run-1/root `
  --run-id run-1 --project-id demo --node-id root --model model-name --seed 7 `
  --review-artifact review.json
```

Use `--validate-only` to write a draft and structured blocking report without calling `input()`. `--resume <session.json>` resumes an interactive session.

Root has only two terminal artifacts: `prd.draft.md` (`FAIL`, never handoff-ready) or `prd.md` (`PASS`, approved, frozen, zero oracle blockers, and a hash-bound independent review).

## Derive

```powershell
python scripts/run_prd_flow.py --parent-prd parent/prd.md `
  --architecture-package architecture --target-module ReservationProcessor --output child/prd.md

python scripts/run_prd_flow.py --derive-all --parent-prd parent/prd.md `
  --architecture-package architecture --output-dir artifacts/run-1
```

Derive inherits only authorized parent obligations. Architecture records determine owner and non-normative reference links; they never create product requirements. Draft parents, incomplete allocations, and invalid projections block output atomically.

Derived identifiers are stable across input ordering: a parent `REQ-001` maps to `REQ-D001`, and `NFR-001` maps to `NFR-D001`. If a source has duplicate parent IDs (an invalid source condition), the collision suffix is a deterministic hash of that parent ID; the parent-to-child mapping is retained in `prd.json` for migration and downstream traceability.

For byte-reproducible experimental artifacts, pass the same `--run-id`, `--model`, `--seed`, and ISO-8601 `--created-at` value on each run. Hashes in the manifest and execution log make provenance independently checkable.

## Artifacts and exits

Every run writes the Markdown PRD plus `prd.json`, `prd_manifest.json`, `validation_report.json`, and `execution_log.json`; blocked Root runs additionally write `blocking_questions.json`. The manifest identifies one shared `artifact_id` for the Architecture and Gherkin consumers.

`execution_log.json` preserves run/project/node identity, timestamps, status/exit code, input/output hashes, model settings, seed, retry/cost placeholders, intervention and blocker counts, and non-sensitive error metadata. `validation_report.json` computes requirement, scope, evidence, oracle, ledger, review, and Derive-projection statistics from the same structured PRD model.

Exit `0` is handoff-ready success; `1` input error; `2` quality/validation block; `3` dependency/configuration error; `4` runtime error; `5` schema/contract incompatibility.
