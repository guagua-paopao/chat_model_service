# ADR-016：安全重试、故障转移与可见输出边界

- Status：Accepted
- Decision date：2026-07-15
- Owners：AI Platform / API / SRE
- Review trigger：路由算法、Provider SLA 或多模型组合需求变化

## Context

429、超时和 5xx 需要自动恢复，但生成请求并非天然幂等；两个模型的文本被无提示拼接会破坏语义、审计和用户信任，并可能重复计费。

## Decision

只有归一化为 retryable 的错误才允许在次数/总时限预算内指数退避加抖动；当前 route 耗尽后可尝试备用 route。每条 route 有独立并发和熔断状态，每次 attempt 单独审计。

一旦任何 `message.delta` 已对用户可见，该请求禁止切换 route 或模型。随后失败则以 error 终止并保存失败状态；用户通过显式 retry 创建新的助手消息。不可重试的 4xx/策略阻断立即终止。

## Consequences

用户可能看到中断而不是自动“补完”，但不会得到来源混杂的伪连续回答。调用 attempt 数量和成本需要监控；生产阈值必须用负载与 Provider 证据校准。
