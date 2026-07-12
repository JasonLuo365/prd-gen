# PRD Gen

PRD Gen 是一个面向分层开发流程的 PRD 生成与评审工具集。它主要覆盖两件事：

- 从产品想法生成顶层 PRD，并通过质量门控补齐可测试边界。
- 基于上层 PRD 和架构包派生下层 PRD，并用 Leaf Gate 判断当前节点是否可以停止拆分进入实现。

当前仓库仍处于迭代阶段，重点是沉淀 PRD 生成 skill、Derive 后端、Leaf Gate 规则和相关测试。

## Repository Layout

```text
prd_flow/                         # PRD 生成 CLI 和 Derive 后端
skills/prd-generation/            # 可复用的 PRD Generation skill 包
leaf-gate-skill/leaf-gate/        # Leaf Gate skill 包
tests/                            # 单元测试和静态 skill 检查
docs/superpowers/specs/           # 流程和 skill 设计文档
outputs/                          # 本地生成物目录，已被 gitignore 忽略
```

## PRD Generation

PRD Generation 分为两种模式。

### Root Mode

Root 模式用于从零生成顶层 PRD。它通过对话收集产品目标、用户、痛点、需求、验收场景和成功指标。

当前 Root 模式的交互策略是选择题优先：

- 每次只问一个决策问题。
- 默认提供几个方向选项。
- 用户可以选择 `Other / supplement` 自由补充或覆盖选项。
- 最终 PRD 必须通过 testcase readiness review，避免把模糊边界留给 testcase 阶段。

### Derive Mode

Derive 模式用于根据上层 PRD 和架构包生成下层 PRD。

推荐命令：

```powershell
.\.venv\Scripts\python.exe -m prd_flow `
  --parent-prd <parent_prd.md> `
  --architecture-package <architecture_dir_or_readme_or_zip> `
  --target-module "<module_or_bounded_context>" `
  --target-granularity auto `
  --output <output_prd.md>
```

`--architecture-package` 支持：

- 架构目录
- 架构目录中的 `README.md`
- `.zip` 架构包
- 旧版单文件 `--parent-architecture` 仍保留兼容

推荐架构包结构：

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

`--target-granularity` 可选：

- `auto`
- `deployable_module`
- `bounded_context`
- `component`

Derive 的首要职责是把父 PRD 的需求无损分发到子 PRD 集合。当前目标明确拥有的父需求、Gherkin、NFR、non-goal，以及前端/Web App、接口、数据库迁移、事件、外部适配器、Worker、运行时集成和观测义务会保留追踪关系并写入子 PRD。每次成功生成还会写出同名的 `*.coverage.json`：父层每项义务都会标记为 `inherited_by_target`、`assigned_to_other_targets` 或 `unassigned`。未分配项会令账本状态为 `allocation_incomplete` 并产生 warning，但不会阻断当前目标；`allocation_complete` 只表示父层义务都有预期子节点，不表示所有子 PRD 文件都已实际生成。输入无效、目标不存在或当前目标无法形成有效子 PRD时才阻断。

## Leaf Gate

Leaf Gate 用于判断一个分层节点是否已经足够清晰，可以停止继续拆分并进入实现。

标准输入是一个节点目录：

```text
node-id/
  prd.md
  testcase.feature
  architecture.yaml|json|md
  traceability.md
  risks.md
```

也支持多文件架构包：

```text
node-id/
  prd.md
  testcase.feature
  architecture/
    output/
      01-system-overview.md
      02-module-partitioning.md
      03-runtime-architecture.md
      04-adr-summary.md
      05-data-model.md
      06-interface-contracts.md
      07-technology-choices.md
      08-deployment.md
    validation-report.md
```

运行 Leaf Gate 时会先执行 prepare evidence：根据当前节点的 PRD、testcase 和架构包自动生成或刷新 `traceability.md` 与 `risks.md`，然后再进入静态检查。`architecture/output` 是主要架构证据；`architecture/validation-report.md` 会作为架构验证、追溯和风险证据一起读取。

`traceability.md` 中的架构证据会标注强度：

- `strong`：直接编号命中，或同时命中架构契约、边界/数值和需求关键词，算覆盖。
- `medium`：命中明确模块/接口/事件和多个需求关键词，算覆盖。
- `weak`：只有泛关键词或部分词命中，不算覆盖。
- `none`：没有可用架构证据，不算覆盖。

`weak` 和 `none` 会让 C4 失败，并返回 `NEEDS_REFINEMENT`，同时通过 `refinement_routes` 指向需要修正的上游产物。

静态检查命令：

```powershell
.\.venv\Scripts\python.exe leaf-gate-skill\leaf-gate\scripts\run_leaf_gate.py `
  <node-dir> `
  --output <node-dir>\leaf-gate.static.json
```

使用 `--output` 时，Leaf Gate 会同时在同目录生成 `leaf-gate.refinement.md` 索引文件。详细修改建议会按责任方拆成 `leaf-gate.refinement.architecture.md`、`leaf-gate.refinement.testcase.md`、`leaf-gate.refinement.owner_decision.md`，只在对应责任方存在时生成。JSON 面向自动化读取，Markdown 面向架构、testcase 和人工决策责任方阅读。

Leaf Gate 不会只靠静态检查返回 `LEAF_READY`。静态检查之后还需要结合 LLM 语义评审，对五个标准给出证据：

- C1 behavior complexity is controlled
- C2 contract boundary is clear
- C3 AI implementation context is controlled
- C4 automatic verification is decidable
- C5 residual risk is low and decomposition gain is low

最终决策只允许：

- `LEAF_READY`
- `NEEDS_DECOMPOSITION`
- `NEEDS_REFINEMENT`

`NEEDS_REFINEMENT` 会携带 `refinement_routes`，把修正反馈分给：

- `architecture`
- `testcase`
- `owner_decision`

## Local Outputs

真实产品 PRD、testcase、architecture、Leaf Gate 报告等生成物建议放在 `outputs/` 下。

示例：

```text
outputs/high-school-math-tutor/
  L0-root/
    prd.md
    testcase.feature
    architecture/
      output/
      validation-report.md
    traceability.md      # Leaf Gate prepare evidence 生成
    risks.md             # Leaf Gate prepare evidence 生成
    leaf-gate.report.json
    leaf-gate.refinement.md              # 修改建议索引
    leaf-gate.refinement.architecture.md # 架构修正建议，仅在需要时生成
    leaf-gate.refinement.testcase.md     # testcase 修正建议，仅在需要时生成
  L1-answer-flow/
    prd.md
```

`outputs/` 已被 `.gitignore` 忽略，不会默认提交到 GitHub。这样可以在本地生成和修改产品文档，同时只把流程代码、skill 和测试推到仓库。

## Development

创建或使用本地虚拟环境后安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

运行重点测试：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_derive `
  tests\test_main_derive.py `
  tests\test_mode_detector.py `
  tests\test_architecture_package_parser.py `
  tests\test_leaf_gate.py `
  tests\test_prd_generation_skill.py
```

运行 Python 编译检查：

```powershell
.\.venv\Scripts\python.exe -m compileall prd_flow skills\prd-generation\scripts\prd_flow tests
```

## Git Notes

常用提交流程：

```powershell
git status
git add -A
git commit -m "describe the change"
git push
```

提交前建议确认 `git status` 里没有出现不想上传的产品生成物。如果生成物放在 `outputs/` 下，默认不会进入 Git。
