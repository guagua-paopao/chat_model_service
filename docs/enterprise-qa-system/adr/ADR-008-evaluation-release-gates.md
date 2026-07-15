# ADR-008：评测作为知识与 AI 配置发布门禁

- Status：Accepted
- Decision date：2026-07-15
- Owners：Product / QA / AI / Security
- Review date：每季度或业务风险变化时

## Context

模型输出具有概率性，主观聊天演示无法证明检索、引用、拒答和权限安全。知识、Parser、Prompt、检索、模型的任一变化都可能让某些切片退化。

## Decision

建立版本化黄金集，包含 answerable、no-answer、ambiguous、ACL、version、numeric 和 injection 切片。影响 RAG/模型/知识的候选发布必须运行相应数据集并通过固定门槛；安全越权为硬失败。报告保存代码、知识、配置、模型、数据集、指标、失败样本、成本和审批。

PR 使用快速集，夜间完整集，发布使用固定 holdout；模型裁判需用人工和确定性规则校准，不能作为唯一真值。

## Alternatives

- 只做人工 UAT：覆盖有限、不可重复、难比较。
- 只看点赞/点踩：反馈有偏且发现太晚。
- 只用单一总分：会掩盖 ACL、无答案和数字等关键失败。

## Consequences

发布速度受到评测时间和成本影响，需要维护数据集；换来可量化质量、回归阻断和可审计风险决定。评测集本身需要数据治理，避免真实隐私泄露和过拟合。

## Baseline Gates

Recall@10 ≥0.85、Groundedness ≥0.90、引用 precision ≥0.90/completeness ≥0.85、无答案 F1 ≥0.85、越权 0。真实业务集建立后可提高或正式校准非安全阈值；越权门槛不可降低。

