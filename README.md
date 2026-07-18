# PRD-Gen-Leaf-Gate

PRD-Gen-Leaf-Gate 是一个面向分层开发流程的 PRD 生成与评审工具集。它主要覆盖两件事：

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

Derive 的唯一职责是依据父架构的直属模块，把父 PRD 的功能需求、排除项、NFR、Acceptance Contract 和指标无损分发到子 PRD 集合。架构仅用于确定模块和归属，不生成新的产品需求。整层生成要求父层条目零遗漏；成功时每个直属模块只写一个 `prd.md`，失败时不写部分结果，也不默认生成索引、账本、错误草稿或审阅文件。

## Leaf Gate

Leaf Gate 只判断一个已经完成前置验证的节点是否还需要继续分层。它不负责修正 PRD、testcase 或架构；这些修正属于前置的“测试用例 Mock 架构验证”闭环。

正式结构化接口的决策/状态只有三种：

- `CONTINUE_LAYERING`：继续生成下层节点。
- `STOP_LAYERING`：不用继续分层，可以进入实现。
- `ERROR`：输入证据、Schema、Mocktest 或深度限制阻止有效判断，不能进入实现。

正式模式需要四个 JSON 输入，且每个产物都保留统一公共字段；`run_id`、`project_id`、`node_id` 和 `schema_version` 必须一致：

```text
node-id/
  prd.json                 # 包含 depth、max_depth、node_history
  architecture.json
  testcases.json
  mocktest_report.json     # 或 leaf_gate_evidence.json
```

正式输出为 `leaf_gate_decision.json`、`leaf_gate_decision.md`、`leaf_gate_metrics.json` 和 `execution_log.json`。旧 Markdown/Feature 流程继续兼容；其 `INPUT_ERROR` 仅是兼容传输状态，在跨模块正式产物中映射为 `ERROR`。

旧版兼容输入是一个节点目录：

```text
node-id/
  prd.md
  testcase.feature
  architecture.yaml|json|md
  traceability.md
  risks.md
```

也支持多文件架构包。当前架构生成器可能直接输出扁平最终包：

```text
node-id/
  prd.md
  testcase.feature
  architecture/
    README.md                   # 可选的包索引/清单
    <最终架构文档...>
```

架构也可以是单文件或嵌套包。Leaf Gate 不固定文件数量、编号、语言、目录名或契约文件名：若存在 README/index/manifest/目录/索引/清单及其本地链接，则优先按清单确定最终包；否则根据系统上下文、运行时、数据与一致性、接口契约、决策和部署等语义选择候选包；非常规或有歧义的结构使用 `--architecture` 显式指定。

架构产物分为四类：

- `primary`：当前有效的最终架构包，可用于 C2 契约和 C4 架构追溯证明。
- `validation`：可选的验证、评审或验收留档，用于风险和来源说明，但不是必需文件。
- `remediation`：修改、整改或修正计划，只表示拟采取的动作，不能证明已经修改完成。
- `supporting`：workbench、生成计划、假设、DDD 分析等支撑材料，默认不作为最终架构证明。

稳定的输入契约是“架构已经通过前置 Mock 验证”，而不是“必须存在 validation-report.md”。验证过程可以已经合入扁平最终架构包，不留下独立报告。

静态报告会记录架构角色清单。角色识别后，Leaf Gate 根据当前节点的 PRD、testcase 和最终架构包自动生成或刷新 `traceability.md` 与 `risks.md`。

`traceability.md` 中的架构证据会标注强度：

- `strong`：直接编号命中，或同时命中架构契约、边界/数值和需求关键词，算覆盖。
- `medium`：命中明确模块/接口/事件和多个需求关键词，算覆盖。
- `weak`：只有泛关键词或部分词命中，属于前置输入错误。
- `none`：没有可用架构证据，属于前置输入错误。

缺少契约字段、追溯缺口、TODO/TBD、开放问题、`weak` 或 `none` 在正式模式均返回 `ERROR`，不会被解释为“继续分层”。旧版兼容模式以 `INPUT_ERROR` 传输同一错误语义；原有上游 Mock 验证流程负责处理这些问题。

旧版兼容静态检查命令：

```powershell
.\.venv\Scripts\python.exe leaf-gate-skill\leaf-gate\scripts\run_leaf_gate.py `
  <node-dir> `
  --output <node-dir>\leaf-gate.static.json
```

如果静态复杂度已经证明继续分层有明显收益，可以直接返回 `CONTINUE_LAYERING`。否则静态报告进入 `STATIC_EVIDENCE` 阶段，`decision` 为 `null`，需要结合 LLM 语义评审后产生最终二元结果。这个阶段不是第三种决策。

五项标准调整为：

- C1 behavior complexity is controlled
- C2 完整契约是否仍横跨多个独立语义边界
- C3 继续分层是否能显著缩小实现上下文
- C4 验证是否仍耦合多个可独立实现的行为
- C5 继续分层的边际收益是否足够高

Leaf Gate 不再生成 refinement 路由或 `leaf-gate.refinement.*.md`。当结果为 `CONTINUE_LAYERING` 时，可以生成 `leaf-gate.decomposition.md`，给出按行为、所有权、契约、一致性或风险边界划分的下层节点建议。

## Local Outputs

真实产品 PRD、testcase、architecture、Leaf Gate 报告等生成物建议放在 `outputs/` 下。

示例：

```text
outputs/high-school-math-tutor/
  L0-root/
    prd.md
    testcase.feature
    architecture/
      README.md
      <最终架构文档...>
    traceability.md      # Leaf Gate prepare evidence 生成
    risks.md             # Leaf Gate prepare evidence 生成
    leaf_gate_decision.json
    leaf_gate_metrics.json
    execution_log.json
    leaf_gate_decision.md
    leaf-gate.decomposition.md # 仅 CONTINUE_LAYERING 时生成
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
