# Architecture Decision Records

本目录保存会影响系统边界、安全、数据、接口、成本或长期维护的重要决策。ADR 一旦 Accepted 不直接删除；被替代时保留原文并指向新的 ADR。

| ADR | 决策 | 状态 |
|---|---|---|
| [ADR-001](ADR-001-modular-monolith-and-worker.md) | 模块化单体 + Worker | Accepted |
| [ADR-002](ADR-002-postgresql-pgvector.md) | PostgreSQL + pgvector | Accepted |
| [ADR-003](ADR-003-rest-and-sse.md) | REST + SSE | Accepted |
| [ADR-004](ADR-004-model-gateway.md) | 统一 Model Gateway | Accepted |
| [ADR-005](ADR-005-tenant-isolation-and-rls.md) | 逻辑租户隔离 + 可选 RLS | Accepted |
| [ADR-006](ADR-006-immutable-document-versions.md) | 不可变文档版本与原子发布 | Accepted |
| [ADR-007](ADR-007-versioned-ai-configuration.md) | Prompt/检索/路由版本化 | Accepted |
| [ADR-008](ADR-008-evaluation-release-gates.md) | 评测作为发布门禁 | Accepted |
| [ADR-009](ADR-009-development-oidc-isolation.md) | 开发 OIDC 与企业身份源隔离 | Accepted |
| [ADR-010](ADR-010-mandatory-tenant-repository-scope.md) | Repository 强制租户与用户作用域 | Accepted |
| [ADR-011](ADR-011-conversation-cursor-and-etag.md) | 会话分页游标与 ETag 并发控制 | Accepted |
| [ADR-012](ADR-012-browser-bff-session.md) | 浏览器 BFF 会话与 CSRF 边界 | Accepted |
| [ADR-013](ADR-013-reproducible-supply-chain-gate.md) | 可复现依赖与供应链门禁 | Accepted |
| [ADR-014](ADR-014-provider-neutral-model-adapters.md) | 供应商中立 Adapter 与批准路由 | Accepted |
| [ADR-015](ADR-015-sse-terminal-events-and-disconnects.md) | SSE 终态、心跳与断线语义 | Accepted |
| [ADR-016](ADR-016-safe-model-retry-and-failover.md) | 安全重试、故障转移与可见输出边界 | Accepted |
| [ADR-017](ADR-017-append-only-usage-ledger.md) | 追加式用量账本与价格快照 | Accepted |
| [ADR-018](ADR-018-shared-quota-and-cancellation-before-production.md) | 多副本前共享配额与取消状态 | Accepted |

## ADR 状态

`Proposed → Accepted → Superseded/Deprecated`。改变外部契约或安全边界前先提交 ADR；紧急事件可以先遏制，但恢复后必须补记。
