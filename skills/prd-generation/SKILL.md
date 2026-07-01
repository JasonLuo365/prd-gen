---
name: prd-generation
description: Use when the user explicitly asks to generate, write, create, or derive a PRD; invokes PRD Generation, Root mode, or Derive mode; or provides parent_prd, architecture_package or parent_architecture, and target_module for lower-level PRD generation.
---

# PRD Generation

## Overview

Use this skill to produce one PRD Markdown document in a reusable layered workflow. The workflow only distinguishes `root` from `derive`; do not invent fixed layer names such as module, component, or subsystem depth unless the source documents already use them.

Root mode is a deep conversational elicitation process. Derive mode is a deterministic backend call that uses the existing `prd_flow` Python code and asks no interactive questions.

## Trigger Mechanism

Only use this skill after an explicit trigger phrase or equivalent clear intent. Mentioning PRD, skill design, requirements, or project ideas is not enough by itself.

Root trigger phrases include:

- "使用 PRD generation skill"
- "调用 PRD 生成 skill"
- "进入 Root 模式"
- "跑 root 示例"
- "生成顶层 PRD"
- "帮我写一个 PRD"
- "为这个项目生成 PRD"

Derive trigger phrases include:

- "进入 Derive 模式"
- "生成下层 PRD"
- "根据上层 PRD 和架构生成模块 PRD"
- Any request that provides `parent_prd`, `architecture_package` or legacy `parent_architecture`, and `target_module`.

Non-trigger phrases include:

- "讨论这个 skill"
- "改进这个 skill"
- "这个 PRD 流程有什么问题"
- "测试这个 skill" when the user has not said they want to run Root mode, Derive mode, or generate a PRD.

If the user says only "测试这个 skill" or otherwise sounds ambiguous, do not trigger PRD generation yet. Ask whether they want to run Root mode as a real PRD-generation session, run Derive mode with parent inputs, or discuss/improve the skill.

## Mode Detection

Choose the mode only after the Trigger Mechanism passes and before collecting content.

| Condition | Mode | Action |
| --- | --- | --- |
| User provides `parent_prd`, `architecture_package` or legacy `parent_architecture`, and `target_module` | Derive | Run the Derive workflow with no interactive questions |
| User says this is a new project, new feature start, or top-level PRD | Root | Start the deep elicitation workflow |
| User only says "write a PRD" or similar | Clarify | Ask whether this is the top-level PRD or a lower-level derivation |

In all modes, the final artifact is a Markdown PRD using YAML frontmatter, Markdown body, and Gherkin acceptance scenarios.

## Root Mode

Use Root mode for the top-level PRD. Do not call external code for Root mode; the LLM performs the dialogue, quality checks, and final assembly.

### Conversation Rules

- Ask one question at a time.
- Use choice-first elicitation in Root mode after the minimal PRD target is known. Present 2-4 mutually exclusive direction options, mark one as the Recommended option when a default is useful, explain the pros and cons of each option, and always include `Other / supplement` so the user can add, combine, or override options with a free-form answer.
- Match the question format to the uncertainty level:
  - When the PRD target is completely unknown, ask one broad orientation question with abstract choices when possible. Use an open question and answer template only when choices would invent a concrete project, product, user group, or pain point.
  - When the user must make a decision, present choice-style options. Treat options as directions, not facts; the selected option authorizes that direction, but the PRD text still needs evidence from the user answer or later confirmation.
  - When enough information exists, summarize the extracted draft and offer confirmation or targeted edit options.
- Do not ask field-by-field form questions. Ask one choice-first decision at a time, extract structure from the user's choice and supplements, then confirm the extracted draft.
- Sharpen vague language inline. If the user says "fast", "friendly", "large scale", "secure", "stable", or a test-blocking qualifier such as "simple" or "complex", immediately propose a quantification, operational definition, or baseline test set.
- Detect necessary but unstated topics as the PRD forms. If the project type implies a requirement area that the user did not mention, ask the user to choose `include` or `not_applicable`; do not silently add it, omit it, or defer it.
- Capture meaningful decisions immediately in an internal decision log, especially trade-offs, thresholds, exclusions, accepted warnings, and any assumption or conflict that can change testcase triggers, boundaries, oracle, or coverage scope.
- Keep testcase evidence locked. Do not invent thresholds, counts, time windows, retry limits, legal/compliance oracle, or scenario Then clauses from common sense. If a value is not present in the PRD, parent input, acceptance text, or an explicit owner decision, record it as a Blocking Question or Change Management item.
- Allow natural-language corrections at any point. Treat them like commands when intent is clear.

Decision-question template:

```markdown
Question: <single decision question>

A. <Option label> (Recommended option)
   Pros: <why this is useful>
   Cons: <trade-off or risk>
B. <Option label>
   Pros: <why this is useful>
   Cons: <trade-off or risk>
C. <Option label>
   Pros: <why this is useful>
   Cons: <trade-off or risk>
D. Other / supplement
   Use when none of the options fit, when multiple options should be combined, or when the user wants to override the recommendation.

You can also answer in your own words; the choices are directions, not facts.
```

Necessary-topic disposition template:

```markdown
Question: <necessary topic> appears relevant because <project-specific reason>. Should this PRD include it?

A. Include it in this PRD (Recommended option when it affects testability, security, compliance, reliability, or core user value)
   Pros: Makes requirements and tests explicit.
   Cons: Adds scope and acceptance criteria to define now.
B. Mark it as not applicable for this PRD
   Pros: Keeps scope narrow and prevents downstream assumptions.
   Cons: The PRD must explicitly state that this version does not cover it.

You can also answer in your own words, but the outcome must be either `include` or `not_applicable`.
```

### Phase Completion Protocol

Each Root phase stops only by quality gate plus user confirmation. The agent controls the quality gate; the user controls whether to proceed, revise, or add more information.

Do not auto-advance when a minimum standard merely appears to pass. When a phase gate passes, stop open-ended elicitation and show a handoff checkpoint:

```markdown
<Phase name> handoff checkpoint

Draft summary:
- <short extracted summary>

Exit checklist:
- [pass/fail] <required condition>
- [pass/fail] <required condition>

Open assumptions or risks:
- <none, or explicit assumption/risk>

A. Proceed to the next phase (Recommended option)
   Pros: <why the phase is ready>
   Cons: <what remains intentionally unresolved, if anything>
B. Add more information
   Pros: <what quality improves>
   Cons: <more time and possible scope growth>
C. Edit a specific field or requirement
   Pros: <targeted correction>
   Cons: <may require rechecking the gate>

You can also answer in your own words or use [DONE].
```

If the user says `[DONE]`, confirms in natural language, or selects the proceed option after the gate passes, move to the next phase. If the user tries to finish before the gate passes, block the transition, list the missing checks, and ask the smallest next question needed to satisfy the gate.

Do not continue asking optional polish questions after a phase passes unless the user chooses to add more information. `[SKIP]` applies only to optional details; it cannot skip a required gate.

Phase exit checklists:

- Frontmatter phase exit checklist:
  - PRD target is clear enough to name the document.
  - `doc_id`, `version`, `layer`, `scope`, `author`, `status`, and `created_at` are non-empty.
  - `layer` is `root`; `scope` describes the document granularity.
- Problem Statement phase exit checklist:
  - `target_users`, `pain_points`, and `opportunity` are non-empty.
  - At least one pain point names a concrete current scenario and failure/friction.
  - Obvious out-of-scope user groups or scenarios are either excluded or recorded as assumptions.
  - Obvious necessary but unstated topics discovered in the problem framing are resolved as `include` or `not_applicable`.
- Requirements phase exit checklist:
  - Core capabilities have been captured from the user.
  - MoSCoW classification has been proposed and accepted or edited by the user.
  - Every functional requirement has `id`, `text`, `priority`, and `source`.
  - At least one functional requirement exists.
  - At least one non-functional requirement exists and has a number or observable threshold.
  - Every necessary but unstated requirement area discovered during requirements has an explicit disposition: `include` with written requirements, or `not_applicable` with a written exclusion/non-goal.
  - Every Must-Have passes Specific, Measurable, and Testable SMART-REQ checks.
  - Every test-blocking qualifier in requirements or NFRs has an operational definition, classification rule, accepted enumeration, or baseline test set.
  - Every test-impacting hypothesis, decision, conflict, or fact has an evidence record with its impact type: `trigger`, `boundary`, `oracle`, `scope`, `exclusion`, or `data set`.
  - No unstated threshold, count, time-window definition, recovery value, or compliance oracle is carried forward without explicit evidence or an owner.
  - Remaining ambiguity is resolved or recorded as an explicit non-blocking assumption/risk.
  - No Blocking Questions remain before moving to Acceptance.
- Acceptance phase exit checklist:
  - Every Must-Have has at least one linked Gherkin scenario.
  - Each scenario has Given, When, and Then.
  - Happy Path is covered; Error Path or boundary behavior is covered when the behavior can fail.
  - Scenario tags include the related `@REQ-XXX` id.
  - Every Given, When, and Then is traceable to PRD/Acceptance text or an explicit evidence record; Then clauses must not contain invented numbers, policies, or oracle.
  - Non-blocking test-impacting items may shape existing scenarios, but must not silently create new scenarios or expand coverage beyond their authorized evidence.
- Success Metrics phase exit checklist:
  - At least one metric exists.
  - Every metric has a target value and measurement method.
  - Every metric that scopes a population with a qualifier has a defined population, measurement start, measurement end, and exclusion rules.
  - Metrics are observable from product behavior, logs, lightweight user feedback, or clearly stated evaluation methods.
  - Final Testcase Readiness Review has been run after Requirements, Acceptance, and Success Metrics are assembled.
  - No Blocking Questions remain after the final review.

### Opening

Start by aligning expectations:

1. State that the PRD will be built around five core parts: Frontmatter, Problem Statement, Requirements, Acceptance, Success Metrics. Quality review, evidence records, and change-management sections may be added to make those five parts testcase-ready.
2. State that functional requirements use MoSCoW priority at the requirement level: Must Have, Should Have, Could Have.
3. State that acceptance criteria use Gherkin and that ambiguous language will be quantified as the conversation proceeds.
4. State that Root mode will primarily use choice questions, and the user can always choose `Other / supplement` or add free-form context.

Then ask what project, product, or feature the user wants a top-level PRD for. If the target is vague, use a broad choice question that does not invent domain facts:

```markdown
Question: What kind of PRD are we creating?

A. New product or system
   Pros: Best when the business goal, users, and scope all need to be shaped.
   Cons: Requires more discovery before requirements can be stable.
B. New feature or module
   Pros: Best when the surrounding product already exists.
   Cons: Requires explicit parent context and integration boundaries.
C. Improvement to an existing flow
   Pros: Best when the current user journey and pain point are already known.
   Cons: Requires current-state evidence and target behavior.
D. Other / supplement
   Use when the request does not fit these directions or needs extra context.

You can also answer in your own words:
I want to build `<system/product/feature>` for `<target users>` to solve `<pain point or goal>`.
```

If the user has already provided the target, skip the broad orientation question and ask the next smallest choice-first question. Do not provide a concrete recommendation before the target is clear.

After the PRD target is clear, ask for or confirm the project name. Generate `doc_id`, `version`, and `scope` from the answer.

### P1 Frontmatter

Collect enough metadata to make the document traceable.

Required fields:

```yaml
doc_id: "<PROJECT-v1.0>"
version: "1.0.0"
layer: "root"
scope: "system"
author: "<author>"
status: "draft"
created_at: "<YYYY-MM-DD>"
tags: []
```

Use `scope` for document granularity. Use `priority` only for individual requirements. If legacy Python output contains frontmatter `priority`, treat it as a compatibility field and explain that the current skill standard prefers `scope`.

Minimum standard: `doc_id`, `version`, `author`, `status`, and `scope` are non-empty.

### P2 Problem Statement

Use choice-first elicitation to clarify the problem shape. Only use a fully open question when there is too little context to create non-leading abstract choices.

Example:

```markdown
Question: Which problem framing is closest?

A. User task is too slow or manual
   Pros: Makes workflow, time cost, and automation value easy to test.
   Cons: Needs current step count, duration, or failure rate.
B. User cannot complete a required action reliably
   Pros: Makes error states, recovery, and success oracle explicit.
   Cons: Needs concrete failure examples.
C. Business or operations team lacks visibility/control
   Pros: Makes reporting, audit, monitoring, and admin needs explicit.
   Cons: Needs owner, data, and permission boundaries.
D. Other / supplement
   Use when the real pain is different or needs more detail.

You can also answer in your own words: who uses this system, in what situation, and what pain are they experiencing now?
```

Extract:

- `target_users`: concrete user group; quantify vague groups such as "small business" or "many users".
- `pain_points`: concrete scenario and current failure or friction.
- `opportunity`: business or user value unlocked by solving the pain.

Minimum standard: all three fields are non-empty, and at least one pain point describes a concrete scenario.

### P3 Requirements

Run five steps.

1. Diverge: offer choice-style capability directions based on the Problem Statement, then ask the user to select, combine, remove, or supplement them. Do not present candidate capabilities as facts until the user confirms them.
2. Classify: propose MoSCoW grouping and explain why each Must Have is necessary.
3. Refine Must-Haves one at a time: ask for supported operations, abnormal cases, and measurable constraints.
4. Add non-functional requirements: propose choice-style options for latency, availability, concurrency, security, logging, and observability only when they are relevant; ask the user to confirm, adjust, or mark them not applicable.
5. Run the necessary-but-unstated scan. For each relevant gap, ask whether to include it or mark it not applicable before moving to Acceptance.

Each functional requirement must include:

```yaml
id: "REQ-001"
text: "<clear behavior>"
priority: "Must Have | Should Have | Could Have"
source: "<user/business/compliance/technical>"
```

Each non-functional requirement must include a number or observable threshold.

Minimum standard:

- At least one functional requirement.
- Every functional requirement has requirement-level `priority`.
- At least one non-functional requirement.
- Every Must-Have passes the mandatory SMART-REQ checks for Specific, Measurable, and Testable.
- No requirement or NFR contains an undefined test-blocking qualifier. If a qualifier controls pass/fail, scenario selection, or performance population, define it before proceeding.
- No necessary but unstated requirement area remains without an `include` or `not_applicable` disposition.

### P4 Acceptance

Do not ask the user to write Gherkin directly. Ask for scenarios in natural language and transform them.

For each Must-Have, gather at least:

- one Happy Path scenario,
- one Error Path or boundary scenario when the behavior can fail,
- a `@REQ-XXX` tag tying the scenario to its requirement.

Acceptance scenarios are evidence-locked:

- Use only authorized PRD/Acceptance text or explicit owner decisions for Given/When/Then.
- If a hypothesis, decision, conflict, or fact changes an existing scenario's trigger, boundary, oracle, scope, exclusion, or data set, reference that evidence record in the scenario tags or nearby rationale.
- A non-blocking item does not automatically produce a new scenario. It may only refine an already-authorized scenario's wording or data if the evidence explicitly supports that refinement.
- If an item requires owner confirmation, do not generate the affected testcase. Put it in the Change Management Backlog until the owner resolves it.
- Do not use `@auto-resolved-assumption`, "reasonable default", or invented pass/fail oracle in `.feature` output.

Scenario template:

```gherkin
Feature: <feature name>
  @REQ-001 @DEC-001 @critical
  Scenario: <observable scenario name>
    Given <precondition>
    When <trigger/action>
    Then <observable result>
```

Minimum standard: each Must-Have has at least one linked Gherkin scenario with Given, When, and Then.

### P5 Success Metrics

Propose candidate metrics from P2 and P3, then ask the user to confirm or adjust.

Each metric must include:

| Field | Requirement |
| --- | --- |
| Metric | Business, technical, or user-success signal |
| Target | Quantified value such as `>= 70%` or `<= 200ms` |
| Measurement | How the value will be measured |

For performance, reliability, accuracy, coverage, or throughput metrics, the measurement description must also state the measurement start, measurement end, test population or baseline test set, and exclusion rules.

Minimum standard: at least one metric, and every metric has both a target value and a measurement method that is ready for testcase generation.

## Derive Mode

Use Derive mode for any lower-level PRD where the parent PRD and architecture package already define the module boundary.

Required inputs:

- `parent_prd`: path or content of the parent PRD.
- `architecture_package`: path to an architecture package directory, the package `README.md`, or a zip containing the architecture Markdown files. The legacy `parent_architecture` single-file input is still accepted for older YAML architecture fixtures.
- `target_module`: exact deployable module or bounded context name, or a close typo that can be resolved from the architecture package.
- `target_granularity`: `auto`, `deployable_module`, or `bounded_context`. Use `auto` by default. If the same name can refer to both a deployable module and a bounded context, block and require an explicit granularity instead of guessing.

Do not require, request, or accept Leaf Gate output as a Derive-mode input. Leaf Gate decides whether another layer is needed before Derive is invoked, and again after the derived PRD, architecture, and testcase exist. Derive itself must work from the parent PRD, architecture package, and target module only.

Architecture package convention:

```text
architecture/
  README.md
  01-system-overview.md
  02-module-partitioning.md
  03-runtime-architecture.md
  04-adr-summary.md
  05-data-model.md
  06-interface-contracts.md
  07-technology-choices.md
  08-deployment.md
```

Default evidence sources:

- Always use `01-system-overview.md`, `02-module-partitioning.md`, `03-runtime-architecture.md`, `05-data-model.md`, and `06-interface-contracts.md` when present.
- Use `04-adr-summary.md`, `07-technology-choices.md`, and `08-deployment.md` when they affect the target module's decisions, technical constraints, deployment, NFRs, risks, or testcase oracle.
- A zip is only a transport form; read it as an architecture package after expanding or indexing the contained Markdown files.

Prefer a deterministic backend over the LLM fallback. Backend lookup order:

1. If this skill package contains `scripts/prd_flow`, use the bundled backend.
2. Otherwise, if the current workspace contains an importable `prd_flow` package, use that local backend.

Bundled backend command from the skill directory:

```powershell
$env:PYTHONPATH = "scripts"
python -m prd_flow --parent-prd <parent_prd> --architecture-package <architecture_package> --target-module <target_module> --target-granularity auto --output <output_prd>
```

Workspace backend command from the repository root:

```bash
python -m prd_flow --parent-prd <parent_prd> --architecture-package <architecture_package> --target-module <target_module> --target-granularity auto --output <output_prd>
```

The backend requires `PyYAML`; in the complete skill package this dependency is declared in `scripts/requirements.txt`. If the current CLI uses a different argument shape, adapt to the local `prd_flow.main` parser but preserve the same logical inputs. Do not ask follow-up questions during Derive. If inputs are missing, report the missing input list and stop.

If `prd_flow` is unavailable, use the self-contained LLM fallback so the skill remains installable outside the original repository. In the LLM fallback:

1. Parse the parent PRD and architecture package from the provided paths or pasted content.
2. Locate `target_module` in the architecture package by exact name first, then by close semantic match within the requested `target_granularity`.
3. If no credible module match exists, stop and report candidate module names instead of inventing a boundary.
4. Extract the module responsibility, granularity, public interfaces, dependencies, related parent requirements, constraints, risks, and source evidence files.
5. Keep only parent requirements owned by the target module according to module responsibility, bounded context ownership, interfaces, data ownership, and events. Do not copy unrelated global requirements into every child PRD.
6. Derive at most one focused child requirement per owned parent requirement. Preserve traceability with `parent_req`, `source`, and requirement-level MoSCoW priority.
7. Exclude orphan parent requirements from the final child PRD unless the architecture evidence clearly assigns them to the target module. Report excluded orphan requirements in logs or a quality report; do not mark them `tentative` and include them by default.
8. Generate focused Happy Path and Error Path Gherkin scenarios tied to child `@REQ-XXX` IDs and parent traces. Merge boundary cases where possible instead of expanding testcase count mechanically.
9. Apply SMART-REQ, evidence-locked testcase, necessary-but-unstated, ambiguity, Gherkin coverage, and the focused Derive quality gates below before finalizing.

Derive mode does not ask interactive follow-up questions. If the parent PRD or architecture package omits a necessary topic for the target module and it cannot be inferred as explicitly in scope or explicitly not applicable, treat the output as quality blocked and report the upstream question. Do not guess a disposition.

### Focused Derive Quality Gates

Derive mode is not a smaller Root mode. Root expands and clarifies an unknown product; Derive narrows an existing parent node into a smaller child PRD. The child PRD may be more specific, but its scope must not expand.

Apply these gates in addition to the general quality gates:

| Gate | Rule | Failure treatment |
| --- | --- | --- |
| Target Boundary Gate | `target_module` must resolve to exactly one deployable module or bounded context in the architecture package. | Input error; list candidate modules. |
| Ownership Gate | Every child requirement must describe behavior owned by the target module's responsibility, interfaces, events, or data boundary. | Exclude unrelated requirements; quality-block if no owned requirements remain. |
| Parent Traceability Gate | Every child functional requirement must cite a parent `REQ-*` or authorized architecture source. | Quality-block missing traces. |
| Scope Compression Gate | The child PRD must use a strict subset of parent behavior and must not repeat global constraints owned by other modules. | Quality-block broad copies or cross-module scope. |
| Implementation Leakage Gate | Technologies, storage choices, workers, ACLs, caches, schema, service accounts, and deployment details must not become PRD Must-Haves unless they define observable behavior or testcase oracle. | Move to architecture handoff or dependencies; quality-block if left as product requirements. |
| Complexity Budget Gate | 3-6 Must-Haves is the healthy range; 7-8 Must-Haves is a warning requiring merge rationale; 9+ Must-Haves is quality-blocked by default. | Merge, narrow, or explicitly split the target before final PRD. |
| Test Projection Gate | A child PRD should normally project to 3-8 acceptance scenarios. If it naturally projects much higher, merge scenarios or block as too broad. | Quality-block uncontrolled testcase expansion. |
| Architecture Projection Gate | Derive may mark architecture concerns for handoff, but must not decide further decomposition. Leaf Gate remains responsible after child architecture and testcase generation. | Keep concerns as handoff notes; do not create another layer. |

Expected backend behavior:

- Parse parent PRD and architecture package directory, README.md, zip, or legacy single architecture file.
- Confirm `target_module` exists at the selected granularity or auto-match close names.
- Extract interfaces, dependencies, related requirements, and orphan requirements.
- Exclude orphan requirements from final output by default.
- Generate one focused child requirement per owned parent requirement with `parent_req`.
- Generate focused requirement and interface scenarios without mechanically multiplying testcase count.
- Run automatic SMART-REQ, focused Derive scope budget, traceability, ambiguity, and Gherkin coverage checks.

Exit code handling:

| Code | Meaning | User-facing response |
| --- | --- | --- |
| 0 | Success | Show output path and summarize generated PRD |
| 1 | Input error | Show missing files, invalid module, or available modules |
| 2 | Quality blocked | Show draft path, error report path, and blocking issues |

## Quality Gates

Run quality gates before finalizing every PRD. Quality gates are not a scoring system. They must either repair the PRD into a testcase-ready state, block final output, or record explicitly out-of-version items in Change Management.

### SMART-REQ

For Must-Have requirements, enforce:

- Specific: concrete action and object, no vague adjectives.
- Measurable: numeric threshold or observable pass/fail condition.
- Achievable: no obviously impossible scale under stated constraints.
- Relevant: ties to the problem statement or `parent_req`.
- Testable: can become a Gherkin scenario or executable assertion.

For Should/Could requirements, enforce Specific and Testable; warn on the rest.

### Testcase Readiness Gate

A test-blocking qualifier is any word or phrase whose meaning decides scenario selection, performance population, priority, error handling, or pass/fail behavior.

Common test-blocking qualifiers include:

- scope and difficulty: simple, complex, common, uncommon, basic, advanced;
- importance: critical, key, major, minor, primary, secondary;
- operating condition: normal, abnormal, high load, large scale, concurrent, frequent;
- quality attribute: timely, fast, stable, reliable, accurate, complete, partial, secure;
- risk class: high-risk, low-risk, sensitive, safe.

Test-blocking decisions also include missing or ambiguous values that decide an existing testcase's:

- trigger: which event starts the scenario, such as the second vs third occurrence of an error;
- boundary: limit values such as the fourth image, second file, fifty-first upload, retry count, timeout, or truncation length;
- oracle: the exact expected result, including legal/compliance pass criteria or whether a rejection/termination is complete;
- scope: whether inputs cover two categories or three categories, natural hour or rolling hour, complete knowledge list or sampled knowledge points;
- recovery: when uploads, retries, auto-switching, or degraded behavior resume normal operation.

Before finalizing a PRD, every test-blocking qualifier in Requirements, Acceptance, or Success Metrics must be replaced with or backed by an operational definition. A valid operational definition includes at least one of:

- a classification rule with concrete thresholds, such as input length, step count, app count, data size, concurrency, or allowed operation types;
- a baseline test set with positive examples and, when useful, negative examples;
- an owner-maintained enumeration, such as a high-risk operation list or low-risk exception list;
- for metrics, target value plus measurement start, measurement end, population or baseline test set, collection method, and exclusion rules.

If a qualifier is unresolved:

1. Stop the phase transition or final generation.
2. Ask the smallest next clarification question, using choice-style options with pros and cons plus free-form input.
3. Record the issue under Blocking Questions until resolved.
4. Do not move it only to Open Questions. Open Questions must not contain unresolved issues that block testcase generation.

Example:

- Blocked: "Simple tasks must generate a plan within 10 seconds."
- Ready: "Simple task means a Telegram text task under 200 characters, involving one bound PC, one authorized local application, no high-risk operation, no file batch processing, no manual takeover, and an expected plan of at most 3 steps. Baseline test set: open calculator, open notepad, create an empty txt file, capture current screen. Plan generation P95 <= 10 seconds from message receipt to plan response."

### Evidence-Locked Testcase Gate

Before finalizing Requirements, Acceptance, or Success Metrics, build a Test Evidence and Decision Register for anything that affects testcase generation.

Use these record types:

| Type | Meaning | Testcase treatment |
| --- | --- | --- |
| `HYP` | Hypothesis or inferred assumption that needs evidence | May shape existing scenarios only after owner authorization; otherwise block or enter Change Management |
| `DEC` | Explicit product, technical, or policy decision | May be used in Given/When/Then and oracle when evidence is cited |
| `CONFLICT` | Contradiction between PRD, parent input, user statement, or acceptance text | Blocks affected scenarios until resolved |
| `FACT` | Source fact, domain constraint, external rule, or owner-provided baseline | May be used only within its stated scope |

For each record, capture:

- `id`: stable ID such as `HYP-001`, `DEC-001`, `CONFLICT-001`, or `FACT-001`.
- `source`: PRD section, parent input, user answer, owner, or external authority.
- `owner`: PO, backend, SRE, legal/compliance, QA, or another accountable role.
- `impact`: one or more of `trigger`, `boundary`, `oracle`, `scope`, `exclusion`, `data set`, `recovery`, or `metric population`.
- `affected_items`: related `REQ-*`, `NFR-*`, Acceptance scenario, or downstream testcase IDs when known.
- `status`: `authorized`, `non_blocking_test_impacting`, `blocking`, or `change_management`.
- `treatment`: how the PRD text, Acceptance, Non-goals, Blocking Questions, or Change Management Backlog handles it.

Rules:

1. `authorized` records may be used directly for testcase execution.
2. `non_blocking_test_impacting` records do not create new scenarios, but they can decide how existing scenarios are written. They still need evidence and must be traceable.
3. `blocking` records stop the affected PRD section or final generation.
4. `change_management` records are not converted into testcase scenarios in the current PRD. Record the owner and the exact decision needed.
5. Never downgrade a missing oracle, undefined boundary, ambiguous time window, unknown compliance criterion, or unresolved input-category conflict to a generic Open Question.
6. Never inject invented values into `.feature` files with tags such as `@auto-resolved-assumption`.

### Final Testcase Readiness Review

Run this review after P5, before emitting the final PRD. Its purpose is to catch testcase-blocking gaps that earlier general quality checks may miss. Do not assign a score.

Review every Requirement, NFR, Acceptance scenario, Success Metric, Non-goal, and evidence record. For each item, actively probe these patterns:

| Pattern | Probe question |
| --- | --- |
| Quantity or upload limit | What happens at `N`, `N+1`, and API bypass? Is the extra item blocked, rejected, ignored, truncated, or partially accepted? |
| Time or frequency limit | Is the window natural, rolling, session-based, or reset by a specific event? When does recovery happen? |
| File or input constraint | Which types, sizes, counts, combinations, corrupt inputs, duplicate inputs, and mixed valid/invalid inputs are allowed? |
| Enumeration or category | Is the list complete, owner-maintained, sampled, or versioned? What happens to unknown categories? |
| State transition | What are valid states, invalid states, repeated actions, cancellation, termination, and restart behavior? |
| Retry or consecutive failure | Which attempt triggers behavior? Does success reset the counter? What is the maximum retry count and final oracle? |
| Partial failure | Does one failed item reject the whole request, skip only the failed item, or produce partial success? |
| Ordering or priority | If only some inputs are processed, what decides "first": selection order, upload order, receive order, timestamp, or priority? |
| Error oracle | What exact state, message, error code, log, audit event, or user-visible result proves the behavior? |
| Metric population | What are measurement start, end, sample population, baseline set, exclusion rules, and aggregation method? |
| Compliance or policy | Which rule source, checklist, reviewer, or owner defines pass/fail? |

For each gap found, follow this repair loop:

1. If the answer can be obtained from the user or owner in the current session, ask the smallest single clarification question with concrete options.
2. After the answer is provided, rewrite the affected PRD sections: Requirements, Acceptance, Success Metrics, Non-goals, Test Evidence and Decision Register, and Change Management Backlog as needed.
3. Re-run the relevant quality gates and this final review on the revised PRD.
4. If the answer cannot be obtained and the affected behavior is in the current PRD scope, add a Blocking Question and do not emit the final PRD.
5. If the owner explicitly says the behavior is out of the current version, add or update a Non-goal and Change Management item, and ensure Acceptance does not generate testcase coverage for it.

Passing condition: the final review passes only when every current-scope testcase-impacting trigger, boundary, oracle, scope, exclusion, data set, recovery rule, and metric population is either authorized in the PRD or blocked from final output.

### Necessary But Unstated Gate

A necessary but unstated topic is any requirement area that is strongly implied by the product domain, risk profile, interfaces, data, users, or acceptance tests, but has not been explicitly included or explicitly excluded by the user or parent inputs.

Use a hybrid mechanism: the checklist below is a coverage aid to prevent missed areas, and the agent's contextual judgment decides which topics are relevant enough to ask about. Do not turn the checklist into a mechanical questionnaire. Ask only when the topic is plausibly necessary for this project and its absence would affect scope, safety, acceptance, testcase generation, compliance, reliability, or downstream implementation decisions.

Scan for these checklist areas before leaving Requirements and again before finalizing:

- identity, authentication, authorization, permission boundaries, and tenant or role separation;
- high-risk operation confirmation, approval, rollback, and safety restrictions;
- error handling, timeout behavior, retries, idempotency, duplicate prevention, and partial failure behavior;
- logging, audit trail, monitoring, alerting, observability, and incident investigation needs;
- performance, availability, concurrency, capacity, rate limiting, backup, recovery, and data retention;
- privacy, sensitive data, security controls, compliance, and data residency;
- external dependency failure, degraded mode, manual takeover, escalation, and support workflow;
- admin operations, configuration, reporting, import/export, and lifecycle management when the product domain implies them.

For each relevant gap, force one of two dispositions:

| Disposition | Required PRD treatment |
| --- | --- |
| `include` | Add concrete functional requirements, NFRs, acceptance scenarios, metrics, or constraints as appropriate. |
| `not_applicable` | Add an explicit exclusion/non-goal stating that this PRD/version does not cover the topic. |

Do not use `defer`, `TBD`, `future consideration`, or a generic Open Question for a necessary topic. If the user will not choose `include` or `not_applicable`, do not create the final PRD; produce a Blocking Questions report instead. The question must ask for that binary disposition and explain why the topic appears necessary.

Every final PRD must include a Necessary Topic Disposition Record. List each necessary-but-unstated topic that was judged relevant, its `include` or `not_applicable` disposition, and where the treatment appears in the PRD. If the contextual scan finds no relevant necessary-but-unstated topics, include a short statement that none were found after scanning the checklist.

Example:

- Gap: Authorized app high-risk operation handling is necessary because the product can control local applications.
- `include`: "The system shall require user confirmation before executing owner-maintained high-risk operations. High-risk operations are listed in `HighRiskOperationList` and include file deletion, external transmission of sensitive files, payment submission, and irreversible account changes."
- `not_applicable`: "This PRD does not cover high-risk local-application operations. The system shall reject such requests and return an unsupported-operation message."

### Ambiguity Scan

Check three layers:

- lexical ambiguity: overloaded terms such as user, order, system, data;
- logic consistency: conflicting latency, consistency, availability, or workflow requirements;
- completeness gaps: missing security, authentication, authorization, error handling, logging, backup, or observability where relevant.
- testcase readiness gaps: undefined test-blocking qualifiers, missing baseline test set, missing metric population, missing measurement start or measurement end.
- necessary-but-unstated gaps: topics that must be dispositioned as `include` or `not_applicable` before final PRD generation.
- evidence gaps: unowned or unauthorized assumptions, conflicts, facts, thresholds, time windows, recovery values, compliance oracle, or scenario Then clauses that would alter testcase execution.

### Gherkin Coverage

Every Must-Have must have a linked scenario. Prefer Happy Path plus Error Path. If a scenario count grows beyond five for one requirement, suggest splitting the requirement. Coverage is not enough by itself: each scenario's trigger, boundary, and oracle must be backed by PRD/Acceptance text or an evidence record.

## Output Contract

Create a single Markdown file. Use this structure unless the user explicitly asks for a different export format.

````markdown
---
doc_id: "<id>"
version: "1.0.0"
layer: "root | derive"
scope: "system | module"
parent_doc: null
author: "<author>"
status: "draft"
created_at: "<YYYY-MM-DD>"
tags: []
---

# Problem Statement

## 目标用户
...

## 痛点描述
...

## 机会窗口
...

# Requirements

## 功能需求

### Must Have
- [REQ-001] ...

### Should Have
- [REQ-002] ...

### Could Have
- [REQ-003] ...

## 非功能需求
- [NFR-001] ...

## 不涉及 / Non-goals
- <Only include when a necessary topic is dispositioned as `not_applicable`; state the exclusion explicitly enough that downstream testcase generation will not assume coverage.>

## 必要内容处置记录
Always include this section in final PRDs. List every checklist topic that was contextually judged relevant but was not originally stated by the user or parent inputs. If none were found, write: `No relevant necessary-but-unstated topics were found after scanning the checklist.`

| Topic | Disposition | PRD treatment |
| --- | --- | --- |
| <authorization> | include | <REQ/NFR/Acceptance links> |
| <high-risk operations> | not_applicable | <explicit non-goal link> |

## Test Evidence and Decision Register
Always include this section in final PRDs. If no test-impacting evidence records exist, write: `No separate test-impacting assumptions, decisions, conflicts, or facts were identified beyond the Requirements and Acceptance text.`

| ID | Type | Status | Impact | Affected items | Evidence / Owner | PRD treatment |
| --- | --- | --- | --- | --- | --- | --- |
| HYP-001 | hypothesis | non_blocking_test_impacting | trigger, oracle | REQ-001 / Acceptance scenario | PO confirmed on <date> | Shapes existing scenario only; does not create a new scenario |
| CONFLICT-001 | conflict | blocking | scope | REQ-002 | PO required | Listed in Blocking Questions; no testcase generated |

## Change Management Backlog
Include this section when an owner must resolve a missing boundary, time window, recovery behavior, compliance oracle, or coverage scope after the current PRD version. If none exist, write: `No Change Management items remain.`

| ID | Related item | Missing decision | Owner | Why testcase generation is blocked | Required PRD update |
| --- | --- | --- | --- | --- | --- |
| CM-001 | HYP-003 / REQ-007 | Natural hour vs rolling hour upload window | PO / Backend | Boundary scenarios cannot be authorized | Define the window and 51st-upload behavior |

## Final Testcase Readiness Review
Always include this section in final PRDs. If it passes, write `PASS`. If any current-scope blocking gap remains, do not emit the final PRD; emit the Blocking Questions report instead.

| Check area | Result | Evidence / notes |
| --- | --- | --- |
| Quantity, boundary, and overflow behavior | PASS | All current-scope limits define `N`, `N+1`, and bypass behavior |
| Time window and recovery behavior | PASS | All current-scope windows define reset and recovery |
| Error oracle and observable results | PASS | Acceptance Then clauses cite PRD text or evidence records |
| Metric population and measurement | PASS | Success Metrics define start, end, population, and exclusions |
| Change Management exclusions | PASS | CM items are excluded from current testcase coverage |

# Acceptance

```gherkin
Feature: ...
  @REQ-001 @DEC-001
  Scenario: ...
    Given ...
    When ...
    Then ...
```

# Success Metrics

| 指标 | 目标值 | 测量方式 |
| --- | --- | --- |
| ... | ... | ... |
````

If Blocking Questions remain, do not create the final PRD. Produce a blocking report instead:

```markdown
# Blocking Questions

| ID | Location | Missing definition | Question to resolve |
| --- | --- | --- | --- |
| BLOCKING-001 | NFR-003 | "simple task" lacks an operational definition and baseline test set | Define simple task by thresholds, examples, or exclusions. |
| BLOCKING-002 | Requirements | Authorization appears necessary but has no disposition | Choose `include` to define authorization requirements, or `not_applicable` to state this PRD does not cover authorization. |
| BLOCKING-003 | REQ-007 | Upload limit says 50 images but does not define natural hour vs rolling hour, 51st image behavior, or recovery timing | PO must define the window, rejection oracle, and recovery rule before testcase generation. |
```

Final PRDs may include only non-blocking assumptions or open questions that do not change testcase trigger, boundary, oracle, scope, exclusion, data set, recovery, or metric population. Open Questions must not contain unresolved issues that block testcase generation, and must not contain necessary but unstated topics without an `include` or `not_applicable` disposition. Use the Change Management Backlog for owner-owned gaps that are intentionally outside the current PRD version.

For Derive documents, add `parent_arch`, `module_name`, `interfaces`, and `dependencies` to frontmatter when available.

## Commands

Support these commands in Root mode:

| Command | Meaning |
| --- | --- |
| `[DONE]` | Finish the current part after minimum standard passes |
| `[BACK]` | Return to the previous part |
| `[EDIT field]` | Modify a named field |
| `[INJECT text]` | Add context or constraints |
| `[EXPLAIN]` | Explain the current recommendation or decision |
| `[STATUS]` | Show progress and concise draft summary |
| `[PAUSE]` | Save current state if the environment supports files |
| `[SKIP]` | Use a default for optional content |

Natural-language feedback is valid. Interpret "go back and change the target users" as `[BACK]` plus `[EDIT target_users]`. `[SKIP]` cannot skip a necessary but unstated topic; it must still be dispositioned as `include` or `not_applicable`.

## Red Flags

- Do not ask field-by-field form questions in Root mode.
- Do not ask multiple unrelated questions at once.
- Do not present a single long recommended answer when the user needs to make a decision; use choice-style options with pros and cons and allow a free-form answer.
- Do not force the user into provided options; every Root-mode choice question must allow `Other / supplement`.
- Do not present choice options as validated facts before the user confirms or edits them.
- Do not invent a concrete project, product, user group, or pain point when the user is only testing or invoking the skill.
- Do not skip a phase quality check before moving on.
- Do not generate architecture or code.
- Do not treat document-level `priority` as the primary layer marker; prefer `scope`.
- Do not continue when a Must-Have fails mandatory SMART-REQ checks unless the user explicitly accepts and records a reason.
- Do not allow an undefined test-blocking qualifier into the final PRD.
- Do not allow an unauthorized testcase trigger, boundary, oracle, scope, exclusion, data set, recovery value, or metric population into the final PRD.
- Do not hide testcase-blocking ambiguity in Open Questions.
- Do not use `@auto-resolved-assumption` or invented "reasonable defaults" in Acceptance or downstream `.feature` scenarios.
- Do not treat non-blocking assumptions as irrelevant to testcase generation; if they affect existing scenarios, record their evidence and impact.
- Do not generate or expand testcase scenarios for Change Management items until the owner updates the PRD.
- Do not emit the final PRD while Final Testcase Readiness Review still has current-scope Blocking Questions.
- Do not merely list testcase-blocking gaps when the user can answer them now; ask, rewrite the PRD, and re-run the review.
- Do not mechanically ask every item in the necessary-but-unstated checklist; use project context to decide relevance.
- Do not use `defer`, `TBD`, or "future consideration" for necessary but unstated topics; force `include` or `not_applicable`, or block final PRD generation.
- Do not mark a necessary topic as `not_applicable` without writing the exclusion/non-goal in the PRD.
- Do not run Derive mode with interactive questions.
- Do not invent requirements that cannot be traced to Root conversation evidence or Derive parent inputs.
- Do not silently discard orphan requirements; either include them as tentative or report why they block quality.
