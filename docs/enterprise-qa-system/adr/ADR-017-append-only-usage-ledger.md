# ADR-017：追加式用量账本与调用时价格快照

- Status：Accepted
- Decision date：2026-07-15
- Owners：FinOps / API / Data
- Review trigger：正式计费、币种/税务或供应商 usage 语义变化

## Context

供应商价格会变化，部分流式响应不返回 usage。若只在消息表保存当前金额或用新价格重算历史记录，无法审计成本；若把 token 估算当真实账单，又会误导 FinOps。

## Decision

成功回答追加一条 `usage_ledger`，保存 input/output/cached token、Provider/model、调用时单价快照、金额、币种和 `estimated`。历史行不因价目表更新而修改。Provider 无 usage 时允许使用统一估算器补齐，但必须 `estimated=true`。

`model_invocations` 记录可靠性 attempt，`usage_ledger` 记录成功回答的成本事实，两者职责分离。S2 Fake 单价仅验证计算，不作为采购/结算依据。

## Consequences

可重放历史成本解释并区分估算质量，但正式供应商对账仍需账单导入、差异核对和财务保留政策；这些不在 S2 范围。
