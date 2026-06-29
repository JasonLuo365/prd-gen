---
name: prd-generation
description: Use when the user explicitly asks to generate, write, create, or derive a PRD; invokes PRD Generation, Root mode, or Derive mode; or provides parent_prd, parent_architecture, and target_module for lower-level PRD generation.
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
- Any request that provides `parent_prd`, `parent_architecture`, and `target_module`.

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
| User provides `parent_prd`, `parent_architecture`, and `target_module` | Derive | Run the Derive workflow with no interactive questions |
| User says this is a new project, new feature start, or top-level PRD | Root | Start the deep elicitation workflow |
| User only says "write a PRD" or similar | Clarify | Ask whether this is the top-level PRD or a lower-level derivation |

In all modes, the final artifact is a Markdown PRD using YAML frontmatter, Markdown body, and Gherkin acceptance scenarios.

## Root Mode

Use Root mode for the top-level PRD. Do not call external code for Root mode; the LLM performs the dialogue, quality checks, and final assembly.

### Conversation Rules

- Ask one question at a time.
- Match the question format to the uncertainty level:
  - When the PRD target is unknown, ask an open question and provide an answer template only. Do not invent a concrete project, product, user group, or pain point.
  - When the user must make a decision, present choice-style options. Include 2-4 mutually exclusive options, mark one as the Recommended option when a default is useful, explain the pros and cons of each option, and explicitly allow a free-form answer.
  - When enough information exists, summarize the extracted draft and offer confirmation or targeted edit options.
- Do not ask field-by-field form questions. Ask open questions, extract structure, then confirm the extracted draft.
- Sharpen vague language inline. If the user says "fast", "friendly", "large scale", "secure", "stable", or a test-blocking qualifier such as "simple" or "complex", immediately propose a quantification, operational definition, or baseline test set.
- Detect necessary but unstated topics as the PRD forms. If the project type implies a requirement area that the user did not mention, ask the user to choose `include` or `not_applicable`; do not silently add it, omit it, or defer it.
- Capture meaningful decisions immediately in an internal decision log, especially trade-offs, thresholds, exclusions, and accepted warnings.
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

You can also answer in your own words.
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
  - Remaining ambiguity is resolved or recorded as an explicit non-blocking assumption/risk.
  - No Blocking Questions remain before moving to Acceptance.
- Acceptance phase exit checklist:
  - Every Must-Have has at least one linked Gherkin scenario.
  - Each scenario has Given, When, and Then.
  - Happy Path is covered; Error Path or boundary behavior is covered when the behavior can fail.
  - Scenario tags include the related `@REQ-XXX` id.
- Success Metrics phase exit checklist:
  - At least one metric exists.
  - Every metric has a target value and measurement method.
  - Every metric that scopes a population with a qualifier has a defined population, measurement start, measurement end, and exclusion rules.
  - Metrics are observable from product behavior, logs, lightweight user feedback, or clearly stated evaluation methods.

### Opening

Start by aligning expectations:

1. State that the PRD will be built in five parts: Frontmatter, Problem Statement, Requirements, Acceptance, Success Metrics.
2. State that functional requirements use MoSCoW priority at the requirement level: Must Have, Should Have, Could Have.
3. State that acceptance criteria use Gherkin and that ambiguous language will be quantified as the conversation proceeds.

Then ask what project, product, or feature the user wants a top-level PRD for. Provide an answer template, not a concrete recommendation:

> I want to build `<system/product/feature>` for `<target users>` to solve `<pain point or goal>`.

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

Ask an open question:

> Who uses this system, in what situation, and what pain are they experiencing now?

Extract:

- `target_users`: concrete user group; quantify vague groups such as "small business" or "many users".
- `pain_points`: concrete scenario and current failure or friction.
- `opportunity`: business or user value unlocked by solving the pain.

Minimum standard: all three fields are non-empty, and at least one pain point describes a concrete scenario.

### P3 Requirements

Run four steps.

1. Diverge: ask the user to list core capabilities in short sentences.
2. Classify: propose MoSCoW grouping and explain why each Must Have is necessary.
3. Refine Must-Haves one at a time: ask for supported operations, abnormal cases, and measurable constraints.
4. Add non-functional requirements: propose defaults such as P99 latency, availability, concurrency, security, logging, and observability; ask the user to confirm or adjust.
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

Scenario template:

```gherkin
Feature: <feature name>
  @REQ-001 @critical
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

Use Derive mode for any lower-level PRD where the parent PRD and parent architecture already define the module boundary.

Required inputs:

- `parent_prd`: path or content of the parent PRD.
- `parent_architecture`: path or content of the parent architecture design.
- `target_module`: exact target module name or a close typo that can be resolved from the parent architecture.

Prefer a deterministic backend over the LLM fallback. Backend lookup order:

1. If this skill package contains `scripts/prd_flow`, use the bundled backend.
2. Otherwise, if the current workspace contains an importable `prd_flow` package, use that local backend.

Bundled backend command from the skill directory:

```powershell
$env:PYTHONPATH = "scripts"
python -m prd_flow --parent-prd <parent_prd> --parent-architecture <parent_architecture> --target-module <target_module> --output <output_prd>
```

Workspace backend command from the repository root:

```bash
python -m prd_flow --parent-prd <parent_prd> --parent-architecture <parent_architecture> --target-module <target_module> --output <output_prd>
```

The backend requires `PyYAML`; in the complete skill package this dependency is declared in `scripts/requirements.txt`. If the current CLI uses a different argument shape, adapt to the local `prd_flow.main` parser but preserve the same logical inputs. Do not ask follow-up questions during Derive. If inputs are missing, report the missing input list and stop.

If `prd_flow` is unavailable, use the self-contained LLM fallback so the skill remains installable outside the original repository. In the LLM fallback:

1. Parse the parent PRD and parent architecture from the provided paths or pasted content.
2. Locate `target_module` in the architecture by exact name first, then by close semantic match.
3. If no credible module match exists, stop and report candidate module names instead of inventing a boundary.
4. Extract the module responsibility, public interfaces, dependencies, related parent requirements, constraints, and risks.
5. Split related parent requirements into lower-level functional requirements. Preserve traceability with `parent_req`, `source`, and requirement-level MoSCoW priority.
6. Carry relevant orphan parent requirements as `tentative: true` when they plausibly belong to the target module; otherwise report them as blocking or out of scope.
7. Generate interface Happy Path and Error Path Gherkin scenarios tied to `@REQ-XXX`.
8. Apply the same SMART-REQ, necessary-but-unstated, ambiguity, and Gherkin coverage quality gates before finalizing.

Derive mode does not ask interactive follow-up questions. If the parent PRD or architecture omits a necessary topic for the target module and it cannot be inferred as explicitly in scope or explicitly not applicable, treat the output as quality blocked and report the upstream question. Do not guess a disposition.

Expected backend behavior:

- Parse parent PRD and parent architecture.
- Confirm `target_module` exists or auto-match close names.
- Extract interfaces, dependencies, related requirements, and orphan requirements.
- Include orphan requirements as `tentative: true` when policy allows.
- Split parent requirements into lower-level functional requirements with `parent_req`.
- Generate interface Happy Path and 400 Error Path Gherkin scenarios.
- Run automatic SMART-REQ, necessary-but-unstated, ambiguity, and Gherkin coverage checks.

Exit code handling:

| Code | Meaning | User-facing response |
| --- | --- | --- |
| 0 | Success | Show output path and summarize generated PRD |
| 1 | Input error | Show missing files, invalid module, or available modules |
| 2 | Quality blocked | Show draft path, error report path, and blocking issues |

## Quality Gates

Run quality gates before finalizing every PRD.

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

### Gherkin Coverage

Every Must-Have must have a linked scenario. Prefer Happy Path plus Error Path. If a scenario count grows beyond five for one requirement, suggest splitting the requirement.

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

# Acceptance

```gherkin
Feature: ...
  @REQ-001
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
```

Final PRDs may include only non-blocking assumptions or open questions. Open Questions must not contain unresolved issues that block testcase generation, and must not contain necessary but unstated topics without an `include` or `not_applicable` disposition.

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
- Do not invent a concrete project, product, user group, or pain point when the user is only testing or invoking the skill.
- Do not skip a phase quality check before moving on.
- Do not generate architecture or code.
- Do not treat document-level `priority` as the primary layer marker; prefer `scope`.
- Do not continue when a Must-Have fails mandatory SMART-REQ checks unless the user explicitly accepts and records a reason.
- Do not allow an undefined test-blocking qualifier into the final PRD.
- Do not hide testcase-blocking ambiguity in Open Questions.
- Do not mechanically ask every item in the necessary-but-unstated checklist; use project context to decide relevance.
- Do not use `defer`, `TBD`, or "future consideration" for necessary but unstated topics; force `include` or `not_applicable`, or block final PRD generation.
- Do not mark a necessary topic as `not_applicable` without writing the exclusion/non-goal in the PRD.
- Do not run Derive mode with interactive questions.
- Do not invent requirements that cannot be traced to Root conversation evidence or Derive parent inputs.
- Do not silently discard orphan requirements; either include them as tentative or report why they block quality.
