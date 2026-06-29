# PRD 生成 Skill 设计文档

**版本:** 1.0.0
**日期:** 2026-06-02
**状态:** 设计中

---

## 1. 概述

### 1.1 设计目标

将现有 PRD 生成流程重构为一个**跨平台兼容的 Skill 文件**，解决 Root 模式"填空题"式交互的浅层问题，实现真正的深度对话式需求挖掘。

核心改进：
- **从被动表单到主动对话**：系统不再逐字段要答案，而是每次提出一个开放式问题，附带推荐答案供用户确认或修正
- **从浅层收集到深度挖掘**：遇到模糊术语即时追问量化，关键决策即时记录，质量检查前置到每个阶段
- **从单一平台到跨平台兼容**：Skill 为纯 Markdown 指令文件，可在 Claude Code、Codex、Gemini CLI 等平台加载使用

### 1.2 背景

现有流程（v2.0）的问题：
- Root 模式按五大部分逐字段收集，本质上是"向导式表单"
- 系统被动等待用户输入，缺乏主动探索和引导
- 质量检查集中在最后，发现问题后需要大面积返工

参考 skill（`devforge-requirement-analysis`）的优势：
- 一次一问 + 推荐答案，降低用户思考负担
- 术语即时量化（sharpen language inline），防止歧义积累
- 决策即时记录（capture decisions immediately），可追溯
- 丰富命令集（APPROVE、ROLLBACK、EDIT、INJECT、EXPLAIN 等），用户有掌控感
- 自然语言反馈支持，不限于预设命令

### 1.3 核心约束

- **必须保留**：PRD 五部分内容结构（Frontmatter、Problem Statement、Requirements、Acceptance、Success Metrics）
- **必须保留**：质量标准（SMART-REQ、歧义扫描、三相格式、MoSCoW 优先级）
- **必须保留**：Derive 模式 v2.0 全自动流水线（调用现有 Python 代码）
- **改造范围**：仅 Root 模式的交互方式

---

## 2. 核心架构

### 2.1 Skill 文件形态

一个主 skill 文件 `prd-generation.md`，**包含 Root 模式的所有交互逻辑**：

- **YAML frontmatter**：`name: prd-generation`，`description: ...`
- **触发条件与模式判定**：写在 skill 正文中，LLM 按规则自动判定
- **Root 模式工作流**：五部分的对话策略、追问规则、推荐答案模板、术语量化触发词库、阶段质检 checklist
- **命令集**：所有支持的命令及其处理逻辑
- **质量标准**：SMART-REQ 五维检查规则、歧义扫描规则、Gherkin 覆盖规则——全部由 LLM 按 skill 指令执行
- **输出模板**：三相文档（YAML frontmatter + Markdown body + Gherkin）的组装模板
- **Derive 模式声明**：触发条件、输入要求、调用方式、退出码含义
- **红旗（Red Flags）**：禁止行为清单

### 2.2 入口与模式判定

**Skill 触发条件：**
- 用户说"我要写 PRD"、"帮我生成需求文档"、"基于 XX 架构设计生成 YY 模块的 PRD" 等

**自动判定（优先级从高到低）：**

1. **用户提供 `parent_prd` + `parent_architecture` + `target_module`** → 进入 **Derive 模式**
2. **用户声明"这是新项目/新功能的开端"** 或 **无上层文档** → 进入 **Root 模式**
3. **模糊输入**（如"帮我写个 PRD"）→ 主动询问："这是项目的最顶层 PRD，还是基于已有 PRD 的下一层细化？"

### 2.3 Root 与 Derive 的分工

| 维度 | Root 模式 | Derive 模式 |
|------|-----------|-------------|
| 触发条件 | 无上层文档 / 项目开端 | 有 parent_prd + parent_arch + target_module |
| 交互方式 | **深度对话**（一次一问 + 推荐答案） | **全自动**（零交互） |
| 实现方式 | **纯 Skill 指令**（LLM 按指令执行） | **调用现有 Python v2.0** |
| 质量检查 | Skill 内嵌规则，LLM 主动执行 | Python 自动修复 + 退出码 |
| 使用场景 | 人工探索需求 | CI/CD 集成 |

### 2.4 与现有代码的集成

| 功能 | 实现方式 |
|------|----------|
| Root 模式全流程 | **Skill 指令**（Markdown） |
| Derive 模式全流程 | **保留 Python v2.0**（确定性要求） |
| Root 模式质量标准 | **Skill 内嵌规则**（LLM 执行） |
| Derive 模式质量门控 | **Python 自动修复 + 报错** |
| 三相文档组装（Root） | **Skill 模板**（LLM 按模板生成） |
| 三相文档组装（Derive） | **Python formatter** |

**设计原则**：Root 模式的对话、追问、质检、格式化全部由 skill 指令驱动 LLM 完成，不调用外部工具。只有 Derive 模式保留现有 Python 代码。

---

## 3. Root 模式 —— 深度对话策略

每个部分遵循统一交互范式：**开放式引导 → 提取结构化信息 → 即时追问补全 → 阶段质检 → 用户确认推进**。

### 3.1 开场三步

**Step 1 — 方法论对齐**
Skill 向用户简要说明：
- "本次将按五个部分逐步构建 PRD：Frontmatter（元信息）→ Problem Statement（问题陈述）→ Requirements（需求规格）→ Acceptance（验收标准）→ Success Metrics（成功指标）"
- "每个需求会被标注 Must/Should/Could 优先级，验收标准使用 Gherkin 格式"
- "对话中我会对模糊术语即时追问量化，对关键决策即时记录"

**Step 2 — 项目初始化（轻量）**
- 询问项目名称
- 询问作者（默认当前用户）
- 初始化 `doc_id`、`version`、`scope`

**Step 3 — 开始第一部分**
进入深度对话循环。

### 3.2 P1. Frontmatter（元信息）

**对话策略：**
- 问题 1："请为这个项目命名" → 用户回答后，skill 自动生成推荐 `doc_id` 和 `version`
- 问题 2："作者是谁？" → 默认推荐当前用户名
- 问题 3："这份 PRD 的范围？" → 推荐 `system`（顶层）或 `module`（模块级）

**阶段质检清单：**
- `doc_id`、`version`、`author`、`status`、`scope` 全部非空
- `doc_id` 符合 `{项目名}-{版本}` 格式

### 3.3 P2. Problem Statement（问题陈述）

**对话策略：**
- **开场问题（开放式）：** "请描述这个系统解决的核心问题：谁会在什么场景下使用它，当前有什么痛点？"
- 从用户回答中提取三个字段：
  - `target_users`：如果用户说"小企业主"，**即时追问量化**："你说的'小企业'具体指员工人数在什么范围？（如 1-50 人）"
  - `pain_points`：提取后确认
  - `opportunity`：如果用户未提及，追问："解决了这个痛点后，能带来什么业务机会或价值？"

**推荐答案：** 基于 P1 的项目名称，skill 主动生成一个初步的问题陈述草稿供用户确认或修改。

**阶段质检清单：**
- `target_users`、`pain_points`、`opportunity` 全部非空
- `target_users` 中无模糊量词（如"很多人"）
- `pain_points` 至少描述了一个具体场景

### 3.4 P3. Requirements（需求规格）—— 核心部分

**对话策略（四步）：**

**Step 1 — 发散收集（开放式）：**
> "请列出这个系统应该具备的所有核心功能，用简短的一句话描述每个。不用担心优先级，先穷尽想法。"

**Step 2 — MoSCoW 分类：**
Skill 对每条需求标注优先级，向用户确认：
> "我将以上需求分类如下，请确认或调整：
> - **Must Have**：用户注册、商品浏览、下单支付（缺少这些系统无法运作）
> - **Should Have**：优惠券系统、订单追踪（重要但可延后）
> - **Could Have**：社交分享、积分兑换（锦上添花）"

**Step 3 — Must-Have 逐条精化（对每条 Must-Have）：**
> "关于'用户注册'，请确认以下细节，或告诉我不同：
> 1. 支持哪些注册方式？（我建议：邮箱 + 手机号 + 微信 OAuth）
> 2. 注册后是否需要邮箱验证？（我建议：需要）
> 3. 密码复杂度要求？（我建议：≥8 位，含大小写字母和数字）"

**术语即时量化（贯穿 Step 1-3）：**

Skill 内置模糊词触发词库，遇到即追问：

| 用户原词 | 追问 |
|---------|------|
| "快速响应" | "具体是多快？≤200ms？≤1s？" |
| "高并发" | "具体是多少？1000 QPS？10000 QPS？" |
| "友好提示" | "具体是什么形式？弹窗？横幅？toast？" |
| "大量用户" | "具体是多少？日活 1 万？10 万？" |
| "安全稳定" | "安全指什么？防 SQL 注入？XSS？稳定指可用性 ≥99.9%？" |

**Step 4 — 非功能需求（主动引导）：**
> "请为系统定义非功能需求。我建议以下默认值，请确认或修改：
> - 性能：关键接口 P99 延迟 ≤ 200ms
> - 可用性：系统可用性 ≥ 99.9%
> - 并发：支持 1000 并发用户"

**决策即时记录：**
- 每条 Must-Have 的纳入决策
- 每个量化阈值的选择（如为什么选 200ms 而不是 100ms）
- 写入 DECISION_LOG（内存中，最终随 PRD 输出）

**阶段质检清单（SMART-REQ）：**
- 至少 1 条功能需求
- 所有功能需求都有 `priority`（Must/Should/Could）
- 至少 1 条非功能需求
- **每条 Must-Have 通过 SMART 五维检查**：
  - S：使用明确动词和具体名词
  - M：包含可量化指标
  - A：在当前约束下可实现
  - R：直接关联业务目标
  - T：可转化为通过/失败判定
- NFR 必须包含具体数值

**未通过处理：**
- 对未通过项，skill 输出修正建议，用户确认后自动应用
- 用户也可选择 `[IGNORE]` 并说明理由

### 3.5 P4. Acceptance（验收标准）

**对话策略：**
- **不要求用户直接写 Gherkin**，而是引导描述场景
- 对每条 Must-Have，按以下模板追问：

> "请描述一个**成功使用**'用户注册'功能的场景：
> - 用户当前处于什么状态？（如：未登录，访问注册页）
> - 用户做了什么操作？（如：输入邮箱、密码，点击注册）
> - 系统应该有什么反应？（如：创建账户，发送验证邮件）"

Skill 实时转化为 Gherkin 格式，用户确认或修改。

- 然后追问 **Error Path**："如果用户输入的邮箱格式无效，系统应该怎么处理？"
- 对关键需求追问 **边界条件**："如果第三方邮箱服务暂时不可用，注册流程应该怎么处理？"

**阶段质检清单：**
- 每条 Must-Have 至少 1 个 Happy Path 场景
- 每条 Must-Have 至少 1 个 Error Path 场景
- 场景语法符合 Gherkin 规范（Given-When-Then）
- 场景与对应需求有 `@REQ-XXX` 标签关联

### 3.6 P5. Success Metrics（成功指标）

**对话策略：**
- 自动从 P3 的 NFR 中提取候选指标（如"≤200ms" → "核心接口 P99 延迟"）
- 主动询问业务指标：
> "请定义 1-3 个业务成功指标。我建议：
> 1. 用户注册转化率 ≥ 70%（基于 P2 的目标用户和 P3 的注册需求）
> 2. 日活用户数（DAU）≥ 1 万（基于 P3 的并发目标推算）
> 请确认或修改。"

- 每个指标追问测量方式："指标'注册转化率'打算怎么测量？埋点统计？A/B 测试？"

**阶段质检清单：**
- 至少 1 个指标
- 每个指标包含：**具体数值目标** + **测量方式**
- 指标与 P3 的需求有直接关联

### 3.7 五部分之间的连贯性机制

- **信息前向传递**：P1 的项目名称用于 P2 的推荐答案；P2 的目标用户用于 P3 的需求推导；P3 的 NFR 用于 P5 的指标推荐
- **信息反向修正**：用户可在任何阶段用 `[BACK]` 回到上一部分修改，后续部分自动重新推导

---

## 4. 命令系统与状态管理

### 4.1 命令集

用户在整个 Root 模式对话中可随时使用以下命令（不区分大小写）：

| 命令 | 作用 | 使用场景 |
|------|------|----------|
| `[DONE]` | 当前部分最低标准已满足，确认并进入下一部分 | 系统提示"最低要求已满足"后使用 |
| `[BACK]` | 回到上一部分修改 | 发现前面内容有误时 |
| `[EDIT 字段名]` | 直接修改当前（或之前）部分的某个字段 | 如 `[EDIT target_users]` |
| `[INJECT 内容]` | 补充额外上下文约束 | 如 `[INJECT 还需要支持国际化]` |
| `[EXPLAIN]` | 解释当前推荐答案或决策的推理 | 用户想知道"为什么推荐 P0" |
| `[STATUS]` | 查看当前进度和已收集内容的摘要 | 长时间对话后回顾进度 |
| `[PAUSE]` | 保存会话状态并退出，下次恢复 | 需要中断时 |
| `[SKIP]` | 跳过当前可选字段，使用默认值 | 非必填项不想回答时 |

**自然语言反馈：**
用户不必严格使用命令，可以直接说自然语言。Skill 解析意图后执行：
- "我觉得注册方式还应该支持微信" → 识别为对 P3 Requirements 的补充，自动 `[INJECT]`
- "回到前面改一下目标用户" → 识别为 `[BACK]` + `[EDIT target_users]`
- "刚才那个延迟推荐值为什么是 200ms" → 识别为 `[EXPLAIN]`

### 4.2 状态管理

**内存状态（对话中维护）：**
```
current_part: "P3"           # 当前进行到哪一部分
completed_parts: ["P1", "P2"] # 已完成部分
draft_content: { ... }       # 五部分的完整草稿
decision_log: [ ... ]        # 关键决策记录
```

**持久化（跨会话）：**
- 用户输入 `[PAUSE]` 时，将状态保存为 `.prd_session_state.md`（YAML + Markdown 混合格式）
- 下次用户启动 skill 时，检测状态文件，询问："检测到未完成的 PRD 会话（已完成 P1、P2），是否继续？"
- 用户也可主动丢弃状态从头开始

**错误处理：**
- 命令不存在 → 提示可用命令列表
- `[DONE]` 但最低标准未满足 → 提示缺失项清单
- `[BACK]` 但已在 P1 → 提示"已在开头，无法回退"

---

## 5. 质量标准 —— Skill 内即时质检

由于 Skill 是纯 Markdown 指令文件，质量标准由 LLM 按 Skill 中详细描述的规则主动执行。

### 5.1 质检触发时机

**每完成一个部分后，Skill 强制要求 LLM 暂停并运行该部分的质检 Checklist**，不通过则不推进。

### 5.2 SMART-REQ 五维检查

**S — Specific（精确性）**
- 检查：需求是否使用了明确动作动词（提供、支持、实现、验证、限制）和具体名词
- 不通过示例："系统应该很快" → **动作**：追问用户并建议修改为"认证接口 P99 延迟 ≤ 200ms"
- 模糊动词触发追问："处理"、"管理"、"支持" → 要求具体化

**M — Measurable（可度量）**
- 检查：是否包含数字、百分比、时间阈值、QPS、并发数等可量化指标
- 不通过示例："体验应该良好" → **动作**：追问"如何定义良好？建议用转化率 ≥ X% 或 NPS ≥ Y"

**A — Achievable（可实现）**
- 检查：在单实例/常规预算/现有技术下是否明显不可行
- 不通过示例："单实例支持 100 亿并发" → **动作**：标记为不可实现，要求拆分或调整

**R — Relevant（相关性）**
- 检查：需求是否与 P2 Problem Statement 中定义的业务目标直接相关
- 不通过示例：电商 PRD 中出现"火星支付支持" → **动作**：追问"这与'提升转化率'有什么关系？"

**T — Testable（可测试）**
- 检查：是否可转化为明确的通过/失败判定
- 不通过示例："系统应具有一致性" → **动作**：建议改为"并发写入同一键，最终返回后完成的值"

### 5.3 分层质检策略

| 需求类型 | 强制检查维度 | 未通过处理 |
|----------|-------------|-----------|
| Must-Have | S + M + T 强制，A + R 警告 | 必须修正后才能推进 |
| Should/Could | S + T 强制，其余警告 | 可标记为 `draft: true` 继续 |
| NFR | M 强制（必须有数值） | 必须补充数值 |

### 5.4 歧义扫描（三层）

**第一层 — 词汇歧义**
- Skill 内置常见歧义词库："用户"（终端/管理员/系统）、"订单"（待付款/已付款/已发货）
- **动作**：遇到后即时追问并统一术语，写入 PRD 的 Terminology 部分

**第二层 — 逻辑一致性**
- 检查：两条需求是否要求互斥行为
- 示例：REQ-002"所有 API ≤ 50ms"与 REQ-008"每请求完整一致性校验"
- **动作**：标记潜在冲突，向用户展示并询问确认

**第三层 — 完整性缺口**
- 对照常见类别检查缺失：认证授权、异常处理、日志监控、数据备份、限流熔断
- **动作**：提示"未检测到安全性相关需求，建议补充或声明'安全性在基础设施层统一处理'"

### 5.5 Gherkin 覆盖检查（P4 专用）

- 每条 Must-Have 至少 1 个 Happy Path + 1 个 Error Path
- 场景使用 Given-When-Then 语法
- 每个场景有 `@REQ-XXX` 标签关联对应需求

### 5.6 质检报告输出格式

每部分质检完成后，LLM 向用户输出：

```
=== P3 Requirements 质检报告 ===
✅ Specific: 全部通过
⚠️ Measurable: 发现 2 处未量化
   - REQ-003 "高并发处理" → 建议改为 "支持 1000 QPS"
   - NFR-001 "快速响应" → 建议改为 "P99 ≤ 200ms"
❌ Testable: 发现 1 处
   - REQ-005 "用户体验友好" → 无法测试，建议改为具体指标
━━━━━━━━━━━━━━━━━━━━
请修正上述问题，或回复 [IGNORE 理由] 跳过警告项。
```

---

## 6. Derive 模式声明

Derive 模式**保留现有 Python v2.0 全自动流水线**，不在 Skill 中重复实现其内部逻辑。

### 6.1 触发条件

用户提供以下三项：
- `parent_prd`：上层 PRD 文档路径或内容
- `parent_architecture`：上层架构设计文档路径或内容
- `target_module`：目标模块名称

### 6.2 Skill 中的声明式入口

Skill 中仅保留以下声明（不含具体实现）：

```
当用户输入包含 parent_prd + parent_architecture + target_module 时：
  1. 确认目标模块存在于架构设计的模块列表中
  2. 调用：python -m prd_flow --mode derive --parent-prd {path} --parent-arch {path} --target {module}
  3. 等待 Python 返回结果（PRD 文件或错误报告）
  4. 向用户展示生成结果或错误信息
```

### 6.3 退出码

| 退出码 | 含义 | 输出 |
|--------|------|------|
| 0 | 成功 | `{parent_id}_{module_name}_prd_v{version}.md` |
| 1 | 输入错误 | 错误信息 + 可用模块列表 |
| 2 | 质量阻塞 | `.draft.md` + `.errors.json` |

---

## 7. 输出规范

### 7.1 文件命名

- Root 层：`{project_name}_prd_v{version}.md`
- Derive 层：`{parent_id}_{module_name}_prd_v{version}.md`

### 7.2 Root 模式三相文档结构

```yaml
---
doc_id: "ECOMMERCE-PLATFORM-v1.0"
version: "1.0.0"
layer: "root"                    # root | derive
scope: "system"                  # system | module
author: "Claude"
status: "draft"                  # draft | review | approved
created_at: "2026-06-02"
tags: ["ecommerce", "platform"]
---
```

```markdown
# Problem Statement

## 目标用户
[精确描述，无模糊量词]

## 痛点描述
[具体场景]

## 机会窗口
[业务价值]

---

# Requirements

## 功能需求

### Must Have
- [REQ-001] 系统应...
  - 来源: [业务方/技术债务/合规]

### Should Have
- [REQ-002] ...

### Could Have
- ...

## 非功能需求
- [NFR-001] 性能: 关键接口 P99 延迟 ≤ 200ms

---

# Acceptance

```gherkin
Feature: 用户注册
  @REQ-001 @critical
  Scenario: 通过邮箱成功注册
    Given 用户未登录且访问注册页面
    When 用户输入有效邮箱 "user@example.com"
    Then 系统创建未验证用户账户
```

---

# Success Metrics

| 指标 | 目标值 | 测量方式 |
| :--- | :--- | :--- |
| 用户注册转化率 | ≥ 70% | 埋点统计 |
```

### 7.3 Derive 层特殊字段

Derive 层 frontmatter 增加追踪信息和接口摘要：

```yaml
---
doc_id: "ECOMMERCE-PLATFORM-v1.0-PAYMENT-GATEWAY-v1.0"
layer: "derive"
scope: "module"
parent_doc: "ECOMMERCE-PLATFORM-v1.0"
parent_arch: "ECOMMERCE-PLATFORM-v1.0-ARCH"
module_name: "payment_gateway"
interfaces:
  - name: "create_payment"
    method: "POST"
    path: "/api/v1/payments"
dependencies:
  - name: "order_module"
    type: "upstream"
---
```

### 7.4 会话状态文件

当用户 `[PAUSE]` 时保存：

```yaml
---
session_id: "sess_20260602_001"
mode: "root"
current_part: "P3"
completed_parts: ["P1", "P2"]
project_name: "ecommerce-platform"
author: "Claude"
created_at: "2026-06-02T10:30:00"
---

# Draft Content

## P1. Frontmatter
[已收集内容]

## P2. Problem Statement
[已收集内容]

## P3. Requirements (In Progress)
[已收集内容]
```

---

## 8. 红旗（禁止行为）

Skill 的"红旗"章节明确列出 LLM 不得执行的行为：

- **禁止**在 Root 模式中逐字段要答案（现有流程的"填空题"反模式）
- **禁止**在 Requirements 阶段一次性抛出多个问题（必须一次一问）
- **禁止**在对话中生成架构设计或代码（只生成 PRD）
- **禁止**跳过阶段质检直接推进到下一部分
- **禁止**忽略用户的 `[BACK]` 或 `[EDIT]` 命令
- **禁止**在 Must-Have 需求未通过 SMART 检查时强制推进
- **禁止**在 Derive 模式中进行任何对话交互（必须全自动）
- **禁止**在 Root 模式中使用 `input()` 或等待程序化输入（必须是自然语言对话）

---

## 9. 设计决策记录

### ADR-001: 为什么 Root 模式用 Skill 指令而非 Python 代码？

**决策**：Root 模式的交互逻辑全部写入 Skill Markdown 文件，由 LLM 按指令执行。

**原因**：
- 对话和追问是 LLM 的天然能力，用代码模拟反而生硬
- Skill 文件可跨平台使用（Claude Code、Codex、Gemini CLI 等）
- 减少维护两套逻辑（代码 + 对话模板）的负担

**后果**：
- 正面：交互更自然，跨平台兼容
- 负面：质检结果不如代码精确（但 Root 模式的质检是"辅助对话"而非"硬性门控"，可接受）

### ADR-002: 为什么 Derive 模式保留 Python 而非提示词化？

**决策**：Derive 模式保留现有 Python v2.0，不改为纯提示词。

**原因**：
- Derive 的核心场景是 CI/CD 集成，需要 100% 确定性和可复现性
- 自动修复、歧义扫描、退出码判断等规则用代码实现更精确
- Python 代码的调试和修复比调整 prompt 更可控

**后果**：
- 正面：确定性最强，CI/CD 友好
- 负面：需要维护少量 Python 代码（仅 Derive 模块）

### ADR-003: 为什么用 `scope` 替代 `priority`？

**决策**：PRD frontmatter 中的 `priority` 字段替换为 `scope`，值为 `system` 或 `module`。

**原因**：
- `priority`（P0/P1/P2）在 PRD 文档级别的含义模糊，与需求级别的 MoSCoW 优先级混淆
- `scope` 更明确地表达 PRD 的层级定位（系统级 vs 模块级）

**后果**：
- 正面：语义清晰，不与其他优先级概念冲突
- 负面：与现有 v2.0 模板的字段名不一致（需在实现时调整）

### ADR-004: 为什么质检规则写入 Skill 而非调用 Python？

**决策**：Root 模式的质量标准（SMART-REQ、歧义扫描、Gherkin 覆盖）以规则形式写入 Skill，由 LLM 执行。

**原因**：
- Root 模式的质检是"辅助对话"，目的是帮助用户完善需求，而非硬性阻断
- LLM 对自然语言的理解足以执行这些规则
- 减少对外部代码的依赖，保持 Skill 自包含

**后果**：
- 正面：Skill 自包含，跨平台兼容
- 负面：质检精度不如代码（但 Root 模式允许 `[IGNORE]` 跳过警告，可接受）
