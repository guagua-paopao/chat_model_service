# ADR-001：模块化单体 + 异步 Worker

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / Backend
- Review date：S4 结束或触发拆分阈值时

## Context

项目需要让团队从零经历身份、会话、知识、检索、模型和治理的完整链路。首版团队预计 6–8 人，业务边界仍在验证，若立即微服务化会增加分布式事务、契约、部署、Trace、版本和 on-call 成本。

文档解析和 Embedding 是长时间、资源波动明显的任务，不能阻塞在线聊天。

## Decision

在线 API 采用模块化单体，内部划分 IAM/Tenant、Knowledge、Retrieval、Conversation、Model Gateway 和 Governance 模块；共享一个 PostgreSQL 实例但不跨模块直接修改表。摄取和评测使用独立 Worker/队列，在线与离线资源隔离。

模块边界使用应用服务接口、Repository 和 Outbox 事件；禁止 handler 直接跨模块访问表。

## Alternatives

- 一开始使用微服务：隔离强，但首期交付与运维成本过高。
- 完全单进程同步任务：简单，但解析高峰会拖垮聊天且难重试。
- Serverless 函数组合：适合部分任务，但本地学习、长 SSE 和一致性更复杂。

## Consequences

优点：本地调试和事务简单、部署少、可快速形成纵切；模块边界仍为未来拆分保留接口。缺点：需要代码评审防止模块耦合，单体发布可能影响多个模块，共享数据库需严格所有权。

## Security and Cost

更少网络边界和凭证降低首期攻击面/平台成本；Worker 必须使用独立数据库角色、队列和资源限制。单体不能成为跳过最小权限的理由。

## Split Triggers

某模块需其他模块 5 倍以上独立扩缩、故障域长期影响 SLO、团队所有权稳定分离、发布节奏冲突或合规要求独立网络/存储时，提交新 ADR。优先考虑拆 Model Gateway 或 Ingestion。

