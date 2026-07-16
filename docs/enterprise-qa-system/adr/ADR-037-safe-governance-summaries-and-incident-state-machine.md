# ADR-037：治理观测使用低基数摘要并以状态机管理安全事件

- 状态：Accepted
- 日期：2026-07-16
- Owner：SRE / Security / AI Quality

## 背景

把 tenant、user、query 或文档标题直接作为指标标签会造成高基数、隐私泄漏和成本失控；只有日志又难以快速判断配额、质量和安全状态。

## 决策

- 管理 API 只返回当前租户、最长 31 天的用量和质量聚合：请求、token、成本、retrieval run、拒答率、引用和反馈。
- 对外摘要不包含 query、Prompt、文档正文、用户邮箱或供应商密钥。
- 安全事件使用 `open → triaged → contained/resolved → closed` 有限状态机，P0～P3、Owner、证据引用、原因、审批和安全处置摘要必填；非法跳转拒绝。
- 仪表盘是辅助界面，生产告警、on-call、SIEM 和长期指标平台必须在目标环境另行接入和验收。

## 后果

治理人员可在不暴露正文的情况下定位趋势，事件流可审计。S5 没有真实 Prometheus/Grafana/值班平台证据，不关闭生产观测 Gate。

