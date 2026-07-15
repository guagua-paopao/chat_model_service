# ADR-004：统一 Model Gateway 和多供应商策略

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / AI Platform
- Review date：S2 Provider 合约测试后

## Context

Chat、Embedding 和 Rerank 提供商的请求、流、错误、用量、数据区域和能力不同。直接在业务代码使用厂商 SDK 会导致字段渗透、难以测试/替换、成本和数据政策分散。

## Decision

领域层只依赖统一 `ModelGateway` 端口。Provider Adapter 负责字段转换、流事件、错误归一化、供应商 request ID、token/成本和能力发现。业务使用 `fast/balanced/quality` 等 route policy，不暴露真实厂商名给普通用户。

路由同时考虑场景、数据分类、能力、健康、预算和区域；fallback 只有在数据政策与能力兼容时允许。至少一个 deterministic Fake Provider 进入全部自动化测试。

## Alternatives

- 直接使用单厂商 SDK：初期快，但锁定严重且故障/测试逻辑散落。
- 直接采用第三方聚合网关：可减少工作量，但仍需评估许可、数据流、能力差异和可观测性。
- 只支持单模型：不满足教学和企业容灾目标。

## Consequences

增加一个适配层和契约测试成本，换来厂商隔离、统一治理、Fake 故障测试和可审计路由。不能假设不同模型输出质量等价；每次路由变化都需评测。

## Security and Cost

密钥只通过 Secret Manager 引用；路由必须执行数据分类，不允许故障时切到未批准外部模型。用量台账记录实际 route/model/price version。

