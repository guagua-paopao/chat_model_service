# ADR-014：供应商中立 Model Adapter 与批准路由

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / AI Platform / Security
- Review trigger：新增 Provider、供应商协议或数据区域变化

## Context

聊天业务若直接依赖厂商 SDK、模型名和错误类型，会把供应商差异扩散到 API、数据库和前端，导致迁移、测试与数据治理困难；但采用完全透明的任意代理又会让未经批准的 endpoint 进入生产。

## Decision

业务层只依赖内部 `ModelAdapter` 协议和归一化事件。Adapter 负责 Provider HTTP/流协议与错误映射，Gateway 负责路由、超时、重试、备用、并发和熔断。公开 API 只接收逻辑 `model_policy`，不接受 endpoint、API key 或任意模型参数。

生产 Fake Provider 永久禁用。外部 Provider 必须显式配置 HTTPS 地址、批准模型和 Secret 注入的 key；配置校验仅是技术控制，不替代供应商、区域、DPA、训练使用和数据分级审批。

## Consequences

新增供应商需要契约测试和路由审批，但领域层保持稳定。OpenAI-compatible 只是线协议兼容标识，不意味着自动信任任何兼容端点。
