# Architecture Decision Records

Accepted ADR 不直接删除；被替代时保留原文并指向新 ADR。改变安全边界、外部契约、数据政策或生产运行方式前，必须先更新 ADR。

| ADR | 决策 | 状态 |
|---|---|---|
| [ADR-001](ADR-001-modular-monolith-and-worker.md) | 模块化单体与独立 Worker | Accepted |
| [ADR-002](ADR-002-postgresql-pgvector.md) | PostgreSQL + pgvector | Accepted |
| [ADR-003](ADR-003-rest-and-sse.md) | REST + SSE | Accepted |
| [ADR-004](ADR-004-model-gateway.md) | 统一 Model Gateway | Accepted |
| [ADR-005](ADR-005-tenant-isolation-and-rls.md) | 租户隔离与可选 RLS | Accepted |
| [ADR-006](ADR-006-immutable-document-versions.md) | 不可变文档版本 | Accepted |
| [ADR-007](ADR-007-versioned-ai-configuration.md) | AI 配置版本化 | Accepted |
| [ADR-008](ADR-008-evaluation-release-gates.md) | 评测作为发布门禁 | Accepted |
| [ADR-009](ADR-009-development-oidc-isolation.md) | 开发 OIDC 隔离 | Accepted |
| [ADR-010](ADR-010-mandatory-tenant-repository-scope.md) | Repository 强制租户作用域 | Accepted |
| [ADR-011](ADR-011-conversation-cursor-and-etag.md) | 游标与 ETag | Accepted |
| [ADR-012](ADR-012-browser-bff-session.md) | 浏览器 BFF 会话 | Accepted |
| [ADR-013](ADR-013-reproducible-supply-chain-gate.md) | 可复现供应链 Gate | Accepted |
| [ADR-014](ADR-014-provider-neutral-model-adapters.md) | Provider 中立 Adapter | Accepted |
| [ADR-015](ADR-015-sse-terminal-events-and-disconnects.md) | SSE 终态与断线语义 | Accepted |
| [ADR-016](ADR-016-safe-model-retry-and-failover.md) | 安全重试与故障转移 | Accepted |
| [ADR-017](ADR-017-append-only-usage-ledger.md) | 追加式用量账本 | Accepted |
| [ADR-018](ADR-018-shared-quota-and-cancellation-before-production.md) | 共享配额与取消状态 | Accepted |
| [ADR-019](ADR-019-quarantine-published-object-boundary.md) | 隔离/发布对象边界 | Accepted |
| [ADR-020](ADR-020-staged-chunks-and-atomic-publication.md) | 分块暂存与原子发布 | Accepted |
| [ADR-021](ADR-021-database-leases-and-outbox.md) | DB lease 与 outbox | Accepted |
| [ADR-022](ADR-022-acl-before-ranking.md) | ACL 先于排名 | Accepted |
| [ADR-023](ADR-023-versioned-ingestion-provenance-and-hash-reuse.md) | 摄取 provenance 与 hash reuse | Accepted |
| [ADR-024](ADR-024-production-ingestion-fail-fast.md) | 生产摄取 fail-fast | Accepted |
| [ADR-025](ADR-025-acl-filtered-hybrid-retrieval.md) | ACL 安全集内混合检索 | Accepted |
| [ADR-026](ADR-026-immutable-rag-config-and-retrieval-snapshots.md) | 不可变 RAG/检索快照 | Accepted |
| [ADR-027](ADR-027-buffer-grounded-output-before-citation-validation.md) | 引用校验前缓冲输出 | Accepted |
| [ADR-028](ADR-028-immutable-citations-with-current-authorization.md) | 不可变引用与当前鉴权 | Accepted |
| [ADR-029](ADR-029-evidence-gated-no-model-abstention.md) | 证据 Gate 拒答 | Accepted |
| [ADR-030](ADR-030-untrusted-source-boundary-and-injection-redaction.md) | SOURCE 不可信边界 | Accepted |
| [ADR-031](ADR-031-exact-pgvector-before-ann.md) | 正确性基线后再用 ANN | Accepted |
| [ADR-032](ADR-032-no-semantic-cache-until-authorization-invalidation-proven.md) | 授权失效证明前禁用语义缓存 | Accepted |
| [ADR-033](ADR-033-server-resolved-groups-and-central-policy.md) | 服务端组与集中策略 | Accepted |
| [ADR-034](ADR-034-rag-config-evaluate-approve-publish-rollback.md) | 配置评测/审批/发布/回滚 | Accepted |
| [ADR-035](ADR-035-database-serialized-shared-quota-leases.md) | DB 串行化配额与租约 | Accepted |
| [ADR-036](ADR-036-tenant-governance-hash-chain.md) | 租户治理哈希链 | Accepted |
| [ADR-037](ADR-037-safe-governance-summaries-and-incident-state-machine.md) | 安全治理摘要与事件状态机 | Accepted |
| [ADR-038](ADR-038-versioned-isolated-evaluation-runs.md) | 版本化、租户隔离评测运行 | Accepted |
| [ADR-039](ADR-039-privacy-safe-opentelemetry-cardinality.md) | 隐私安全低基数 OTel | Accepted |
| [ADR-040](ADR-040-slo-burn-rate-alerts-and-runbooks.md) | SLO 燃尽告警与 Runbook | Accepted |
| [ADR-041](ADR-041-bounded-local-load-and-fault-harness.md) | 有界本地压测与故障注入 | Accepted |
| [ADR-042](ADR-042-restore-proof-over-backup-success.md) | 恢复证明优先于备份状态 | Accepted |
| [ADR-043](ADR-043-separate-process-snapshot-ledger-and-slo-evidence.md) | 快照、账本与 SLO 证据分层 | Accepted |

状态流转：`Proposed → Accepted → Superseded/Deprecated`。
