# 通用分层开发 Vibe Coding 流程

## 1. 定位

本文描述一套用于分层开发产物的通用 vibe coding 流程。

它适用于已经完成分层拆解和 Leaf Gate 判断的项目。也就是说，本流程不负责判断某个节点是否继续拆分，不负责决定哪个节点是 leaf；这些都由前置的分层开发流程和 Leaf Gate 完成。

本流程只处理一个问题：

> 当多个 Leaf Ready 节点已经具备实现条件后，如何用 AI 或多人协作进行低成本开发，并保证子节点逐层回填到父节点时不发生契约不兼容。

核心原则：

> Leaf Gate 决定能不能开始写；Vibe Coding 流程决定怎么写才不会在回填时失控。

## 2. 适用输入

每个进入本流程的 leaf 节点，应至少具备以下产物：

- `prd.md`：当前 leaf 的需求和边界。
- `architecture/output/`：当前 leaf 的架构产物。
- `architecture/output/06-interface-contracts.md` 或等价契约文件。
- `*.feature` 或等价验收场景。
- `traceability.md`：需求、测试、架构之间的追溯关系。
- `risks.md`：实现风险和缓解措施。
- `leaf-gate.report.json`：Leaf Gate 通过记录。
- `owner-decision.md`：如存在，则优先级高于普通需求和架构说明。

父层节点应至少提供：

- 父层对该 child 的期望契约。
- 父层集成位置。
- 父层验收场景或集成测试要求。
- 与 sibling 节点交互时的共享 API、事件、状态、错误码、数据模型和性能口径。

## 3. 通用层级模型

本流程不假设项目只有两层。项目可以是任意深度：

```text
Root
  -> L1
    -> L2
      -> L3
        -> Leaf
```

一个节点在 vibe coding 阶段只有两种身份：

- **Leaf**：已经通过 Leaf Gate，可以独立实现。
- **Integration Node**：接收一个或多个已完成 child 的父节点。

当一个 Integration Node 的所有必要 child 都回填并通过验证后，它自身可以作为更高层父节点的 completed child，继续向上回填。

因此，回填是递归的：

```text
Leaf 完成
  -> 回填到 Parent
  -> Parent 验证通过
  -> Parent 作为 completed child 回填到 Grandparent
  -> 一直回填到 Root
```

## 4. 角色分工

多人或多 AI 协作时，建议使用以下角色。

### 4.1 Integration Owner

Integration Owner 负责总控和回填。

职责：

- 接收 Leaf Gate 输出目录。
- 生成执行矩阵。
- 决定哪些 leaf 可以并行，哪些 leaf 必须串行。
- 为每个 Leaf Owner 分发 `vibecode-task`。
- 维护冻结的父层契约。
- 接收 leaf 完成包。
- 执行逐层回填。
- 跑父层兼容性检查和最终验收。
- 处理或升级契约冲突。

Integration Owner 可以是一个人，也可以是一个主 AI 线程。

### 4.2 Leaf Owner

Leaf Owner 负责某个 leaf 或一组 leaf 的实现。

职责：

- 只读取分配给自己的 leaf 上下文和允许读取的父层契约。
- 不扩大 leaf scope。
- 不直接修改父节点 wiring、全局共享契约或 sibling 内部实现。
- 先搭建 leaf 的契约骨架。
- 实现 leaf 内部逻辑。
- 跑 leaf verification。
- 生成 Child Completion Package。

Leaf Owner 可以是开发者，也可以是独立 AI 线程。

### 4.3 Contract Owner

Contract Owner 负责契约裁决。

职责：

- 判断契约冲突是否需要修改 leaf、adapter、父层契约或版本。
- 审批 contract change request。
- 判断契约变更影响哪些 sibling 或上层节点。
- 维护契约版本策略。

小团队中，Contract Owner 可以由 Integration Owner 兼任。

### 4.4 Reviewer / QA

Reviewer / QA 负责抽查质量。

职责：

- 检查关键 leaf 的 completion report。
- 抽查 contract diff。
- 复核高风险节点的测试结果。
- 参与最终验收。

该角色可选。低成本模式下可以由 AI 自动生成报告，人工只看失败项和高风险项。

## 5. 人次操作模型

本流程的目标不是让人逐项手工执行 checklist，而是把 checklist 变成 AI 或工具的执行规范。

人工只出现在波次边界和异常边界。

### 5.1 单人或单主控模式

若一个人或一个主 AI 线程控制整个项目：

```text
人工操作次数 = 2 + Leaf 实现波次数 + 回填层级波次数 + 异常决策次数
```

说明：

- `2`：启动项目和批准执行矩阵。
- `Leaf 实现波次数`：把所有 leaf 分成几批开发。
- `回填层级波次数`：从 leaf 回填到 root 经过多少层。
- `异常决策次数`：契约冲突、测试失败、需求不清时才发生。

示例：

```text
Root -> L1 -> L2 -> Leaf
```

若所有 leaf 一批并行开发，回填层级是三层：

```text
Leaf -> L2
L2 -> L1
L1 -> Root
```

没有异常时，人工操作约为：

```text
2 + 1 + 3 = 6 次
```

### 5.2 多人协作模式

若有 `M` 个 leaf，由多个 Leaf Owner 分散实现，回填层级为 `D`：

低自动化模式：

```text
总人次 = Integration Owner 的 2 + D 次 + 每个 Leaf Owner 的 2 次
      = 2 + D + 2M
```

高自动化模式：

```text
总人次 = Integration Owner 的 2 + D 次 + 每个 Leaf Owner 的 1 次
      = 2 + D + M
```

多人模式下的关键规则：

> 开发可以分散，契约和回填必须集中。

Leaf Owner 不直接回填父节点，只交付 Child Completion Package。父节点 wiring、共享契约、全局路由、事件总线和集成测试由 Integration Owner 统一处理。

## 6. 整体流程

### 阶段 0：启动

操作者：Integration Owner

输入：

- Leaf Gate 输出目录。
- 目标代码仓库。
- 并行策略。
- 技术栈约束。
- 是否允许自动创建分支或工作区。

人工操作：

```text
请基于这个 Leaf Gate 输出目录启动 vibe coding。
模式：多人并行优先，严格契约回填，异常再问我。
```

AI 或工具自动执行：

- 扫描所有 `LEAF_READY` 节点。
- 读取每个 leaf 的 gate report、contract、feature、risks。
- 读取必要父层 contract。
- 构建 leaf 清单。
- 构建依赖图。
- 标记可并行和必须串行的节点。
- 生成执行矩阵。

输出：

- `vibecode/execution-matrix.md`
- `vibecode/integration-map.md`
- `vibecode/global-contract-index.md`

### 阶段 1：批准执行矩阵

操作者：Integration Owner，可带 Contract Owner

人工操作：

- 确认哪些 leaf 第一批做。
- 确认哪些 leaf 需要等依赖完成。
- 确认父层契约冻结位置。
- 确认异常处理策略。

AI 或工具自动执行：

- 为每个 leaf 生成 `vibecode-task.md`。
- 为每个 leaf 生成 `allowed-context.md`。
- 为每个 leaf 生成 `forbidden-changes.md`。
- 为每个 leaf 生成 verification checklist。
- 为每个 leaf 准备 contract skeleton 计划。

输出：

```text
vibecode/
  leaves/
    <node-path>/
      vibecode-task.md
      allowed-context.md
      forbidden-changes.md
      contract-checklist.md
      implementation-checklist.md
      verification-checklist.md
      backfill-target.md
```

其中 `<node-path>` 应支持任意深度，例如：

```text
root.identity.otp-verification
root.tutoring.ai.hint-generation
root.billing.invoice.pdf-renderer
```

### 阶段 2：Leaf 实现波次

操作者：Leaf Owner

每个 Leaf Owner 的人工操作：

```text
请执行这个 leaf 的 vibecode-task，严格遵守 allowed-context、forbidden-changes 和 contract。
```

AI 自动执行：

- 读取 `vibecode-task.md`。
- 只读取 `allowed-context.md` 中列出的文件。
- 建立或确认 contract skeleton。
- 建立 fake/mock dependencies。
- 写 contract tests。
- 按 feature 场景实现 leaf 内部逻辑。
- 跑 leaf tests。
- 跑 contract tests。
- 跑风险清单检查。
- 生成完成报告。

Leaf Owner 不应执行：

- 修改父节点 wiring。
- 修改 sibling 代码。
- 修改全局共享 contract。
- 直接改 root-level DTO 或 event schema。
- 引入超出 leaf scope 的业务行为。

输出：

```text
vibecode/leaves/<node-path>/
  completion-report.md
  contract-diff.md
  test-results.md
  risk-resolution.md
  child-completion-package.md
```

### 阶段 3：Leaf 完成确认

操作者：Leaf Owner，可由 Reviewer / QA 抽查

人工操作：

- 查看失败测试是否为零。
- 查看 `contract-diff.md` 是否存在 breaking mismatch。
- 查看 `risk-resolution.md` 是否遗留高风险。
- 确认该 leaf 可以提交给 Integration Owner 回填。

高自动化模式下，Leaf Owner 可以只确认 AI 给出的结论：

```text
该 leaf 是否满足 completion criteria？
```

通过条件：

- 所有 leaf-owned tests 通过。
- provider contract tests 通过。
- consumer-facing schema 与父层期待一致。
- 无未解决高风险。
- 无未经批准的 contract change。

### 阶段 4：第一层回填

操作者：Integration Owner

人工操作：

```text
开始把本批完成的 leaf 回填到直接父节点。
```

AI 或工具自动执行：

- 读取每个 Child Completion Package。
- 读取父节点 child slot。
- 执行 contract diff。
- 若无冲突，替换父节点中的 mock/fake child。
- 在父节点 assembly / adapter / wiring 层注册真实 child。
- 接入 route、provider、event publisher、event consumer、DI/container、配置、日志、metrics。
- 保持 sibling 继续使用 fake，避免一次集成范围过大。
- 跑父节点 compatibility check。

父节点允许修改的位置：

- integration wiring
- adapter binding
- module registry
- route registration
- event subscription registration
- test fixtures
- parent integration tests

父节点不应修改的位置：

- sibling 内部实现
- leaf 内部实现
- 未经批准的共享 contract
- 与本次回填无关的业务逻辑

输出：

```text
vibecode/backfill/<parent-node-path>/
  backfill-plan.md
  contract-diff-summary.md
  integration-wiring-report.md
  compatibility-check-report.md
  backfill-report.md
```

### 阶段 5：父节点兼容性检查

操作者：Integration Owner，必要时 Reviewer / QA 参与

AI 或工具自动执行：

- child provider contract test
- parent consumer contract test
- parent integration test
- sibling fake collaboration test
- parent feature smoke test
- regression smoke test

通过条件：

- 父节点通过所有必要 child 的 contract compatibility。
- 父节点可以通过契约调用 child。
- 父节点不依赖 child 内部实现。
- sibling 之间没有直接耦合。
- 父节点 feature smoke test 通过。

若父节点所有必要 child 都已回填并通过，则父节点状态变为：

```text
COMPLETED_CHILD_READY
```

该父节点随后可以作为更上层节点的 child 继续回填。

### 阶段 6：逐层向上回填

操作者：Integration Owner

人工操作：

```text
继续向上一层回填。
```

AI 或工具自动执行：

- 把已完成父节点视为 child completion package。
- 读取更高层父节点的 child slot。
- 重复 contract diff、wiring、compatibility check。
- 直到 root。

对于任意深度项目，该阶段重复执行：

```text
Completed Child
  -> Parent child slot
  -> Contract diff
  -> Wiring
  -> Compatibility check
  -> Parent becomes Completed Child
```

### 阶段 7：最终验收

操作者：Integration Owner，可带 Reviewer / QA

人工操作：

```text
执行最终验收并生成总报告。
```

AI 或工具自动执行：

- 跑 root-level smoke tests。
- 跑关键 E2E 流程。
- 跑跨模块 contract tests。
- 跑事件流验证。
- 跑性能口径相关 smoke。
- 汇总所有 leaf completion report。
- 汇总所有 backfill report。
- 生成最终报告。

输出：

```text
vibecode/final-report.md
```

最终报告应包括：

- 完成的 leaf 列表。
- 每层回填结果。
- 通过的测试清单。
- 未解决风险。
- contract change 记录。
- deferred items。
- 是否建议进入发布、人工验收或下一轮修复。

## 7. 回填的定义

回填不是复制代码，也不是让 leaf 直接修改父节点内部。

回填的准确定义是：

> 将 child 已实现能力接入父节点预留的集成位置，并证明 child 的实际交付满足父节点原定契约。

推荐模式：

> Replace Mock With Real Child

父节点在 leaf 开发前应使用 mock/fake child。leaf 完成后，Integration Owner 在父节点 wiring 层把 mock/fake 替换成真实 child，然后跑兼容性检查。

## 8. Child Completion Package

每个 leaf 交付给 Integration Owner 的完成包应包括：

- leaf 对外 API、adapter 或 callable entrypoint。
- DTO、schema、event、error mapping。
- 状态机说明。
- side effects 说明。
- dependencies 说明。
- migrations 或初始化脚本，如有。
- fake/mock 替换说明。
- leaf test 结果。
- contract test 结果。
- risk resolution。
- completion report。

建议文件：

```text
child-completion-package.md
contract-diff.md
test-results.md
risk-resolution.md
completion-report.md
```

## 9. Contract Diff

回填前必须执行 contract diff。

对比对象：

- 父节点期待的 child contract。
- child 实际交付的 public contract。

检查项：

- API 路径、方法、请求字段、响应字段。
- DTO 字段名、类型、必填性、枚举值。
- 事件名、事件版本、payload、idempotency key。
- 错误码、错误语义、降级策略。
- 状态枚举、状态转移。
- 权限和认证要求。
- side effects。
- dependencies。
- 性能口径。
- 超时、重试、幂等规则。

结果分类：

- `MATCH`：完全兼容。
- `ADDITIVE_ONLY`：child 多实现了内容，但未暴露给父层或不破坏契约。
- `ADAPTER_NEEDED`：可通过 adapter mapping 解决。
- `LEAF_FIX_REQUIRED`：leaf 未满足父契约，应修 leaf。
- `CONTRACT_CHANGE_REQUIRED`：父契约需要变更，必须走契约变更流程。

## 10. 契约冲突处理

发生冲突时，不允许 Leaf Owner 私自修改父契约。

处理顺序：

1. 若 leaf 没实现父契约：修 leaf。
2. 若 leaf 字段命名或格式不同但语义相同：优先加 adapter mapping。
3. 若 leaf 多实现内容：保留在 leaf 内部，不暴露给父节点。
4. 若父契约含糊：补充 contract clarification。
5. 若确实需要改契约：提交 contract change request。

Contract Owner 裁决：

- 是否允许 contract change。
- 是否需要新版本。
- 哪些 sibling 受影响。
- 哪些父层测试需要更新。
- 是否阻塞当前回填波次。

## 11. 分支和工作区策略

多人模式建议：

```text
main
  -> integration/<project-or-wave>
  -> leaf/<node-path>
  -> leaf/<node-path>
  -> leaf/<node-path>
```

规则：

- Leaf Owner 在 leaf 分支或独立工作区开发。
- Leaf Owner 不直接合并到 main。
- Leaf Owner 完成后提交 Child Completion Package。
- Integration Owner 在 integration 分支统一回填。
- 回填通过后再进入 main 或发布分支。

低成本单人模式可以不创建大量分支，但仍应逻辑上区分：

- leaf implementation
- parent backfill
- root verification

## 12. 可并行和必须串行的判断

可以并行：

- 不共享同一个父节点内部状态机的 leaf。
- 只通过冻结契约交互的 sibling。
- 只依赖 mock/fake 外部系统的 leaf。
- 共享契约已冻结且无待决问题的 leaf。

应串行：

- 依赖同一个未冻结契约的 leaf。
- 需要先实现基础 shared kernel 的 leaf。
- 同时修改同一个父节点 wiring 的回填动作。
- 强依赖上游真实实现结果的 leaf。

经验规则：

> Leaf 实现可以尽量并行，回填尽量按父节点集中串行。

## 13. 人类操作清单

### 13.1 Integration Owner 操作

最少需要：

1. 启动 vibe coding。
2. 批准执行矩阵。
3. 启动每一层回填。
4. 执行最终验收。
5. 处理异常。

典型命令：

```text
请基于这个 Leaf Gate 输出目录启动 vibe coding。
```

```text
批准这个执行矩阵，开始第一批 leaf 实现。
```

```text
开始把第一批完成 leaf 回填到直接父节点。
```

```text
继续向上一层回填。
```

```text
执行 root 验收并生成最终报告。
```

### 13.2 Leaf Owner 操作

高自动化模式下，每个 Leaf Owner 最少只需要一次操作：

```text
请执行分配给我的 vibecode-task，完成后生成 Child Completion Package。
```

低自动化模式下，每个 Leaf Owner 通常两次操作：

1. 启动 leaf 实现。
2. 确认 completion report 可以提交回填。

Leaf Owner 不需要手工做：

- 生成上下文清单。
- 复制父层 contract。
- 生成 mock/fake。
- 对比 API 字段。
- 编写完成报告初稿。
- 判断 sibling 影响面。

这些应由 AI 或工具自动完成。

### 13.3 Contract Owner 操作

只在异常时介入：

```text
这个 contract diff 出现 CONTRACT_CHANGE_REQUIRED，请裁决。
```

Contract Owner 输出：

- reject，要求 leaf 适配现有契约。
- approve adapter mapping。
- approve contract clarification。
- approve contract version bump。
- block，要求重新设计相关契约。

## 14. 最小可行实现形态

第一版不建议直接做重型平台。推荐三层实现：

### 14.1 Playbook

即本文这类手册，定义人和 AI 如何协作。

### 14.2 Templates

为每个 leaf 和 backfill 生成固定 Markdown 模板：

```text
vibecode-task.md
allowed-context.md
forbidden-changes.md
contract-checklist.md
implementation-checklist.md
verification-checklist.md
child-completion-package.md
backfill-plan.md
contract-diff.md
backfill-report.md
final-report.md
```

### 14.3 Automation

后续可做 CLI 或脚本：

- 从 Leaf Gate 输出生成执行矩阵。
- 自动生成 leaf task。
- 自动提取契约索引。
- 自动做 schema diff。
- 自动跑测试。
- 自动生成报告。

自动化不是第一天必须完成，但模板名称和字段应从一开始稳定下来，方便后续升级成工具。

## 15. 质量底线

无论单人还是多人，以下规则不能省略：

- Leaf Owner 只能实现 leaf scope。
- 父层契约只读，除非走 contract change。
- Leaf 完成必须有 completion report。
- 回填必须先做 contract diff。
- 回填只改 integration layer。
- 兄弟节点之间不能直接依赖内部实现。
- 每层回填都必须跑 compatibility check。
- 只有通过父节点验证的 child 才能继续向上回填。

## 16. 一句话总结

这套流程把分层开发后的 vibe coding 分成两条线：

- **分散实现**：每个 Leaf Owner 低上下文、低成本地实现自己的 leaf。
- **集中回填**：Integration Owner 按契约逐层集成，保证多人和多 AI 并行开发后仍能组合成一个一致系统。

最终目标不是减少所有步骤，而是减少人类手工参与，把大部分步骤交给 AI 和工具执行，让人只在启动、批准、回填波次和异常裁决时介入。
