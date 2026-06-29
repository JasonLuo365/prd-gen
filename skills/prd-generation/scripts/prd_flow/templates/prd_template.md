---
doc_id: "{{doc_id}}"
version: "{{version}}"
layer: "{{layer}}"
parent_doc: {{parent_doc}}
author: "{{author}}"
status: "{{status}}"
priority: "{{priority}}"
created_at: "{{created_at}}"
tags: {{tags}}
---

# Problem Statement

## 目标用户
{{target_users}}

## 痛点描述
{{pain_points}}

## 机会窗口
{{opportunity}}

---

# Requirements

## 功能需求

### Must Have
{{must_have_reqs}}

### Should Have
{{should_have_reqs}}

### Could Have
{{could_have_reqs}}

## 非功能需求
{{non_functional_reqs}}

---

# Acceptance

```gherkin
{{gherkin_scenarios}}
```

---

# Success Metrics

| 指标 | 目标值 | 测量方式 |
|:---|:---|:---|
{{success_metrics}}
