# S2 Gate 评审

> 评审日期：2026-07-15  
> 决定：**Conditional GO — 允许 S3 合成知识摄取开发；禁止真实数据、真实 Provider 扩大使用、多副本 staging 和生产**

## 1. 退出条件

| 条件 | 结果 | 证据/说明 |
|---|---|---|
| Provider-neutral Gateway 与至少两个 Adapter 契约 | 通过 | Deterministic Fake + OpenAI-compatible MockTransport；领域层无厂商 SDK |
| REST + SSE 稳定契约 | 通过 | OpenAPI、契约测试、10 事件全栈 smoke、15 秒心跳 |
| 错误归一化、超时、重试、备用、熔断 | 通过（合成） | 429/超时/阻断/中断/全失败自动化；真实 Provider 未测 |
| 可见 delta 后不跨模型拼接 | 通过 | 单测覆盖，ADR-016 固化 |
| 消息、attempt、usage/cost 可审计 | 通过（合成） | PostgreSQL migration + smoke 计数 + estimated usage 测试 |
| 取消、断线与重试 | 条件通过 | 状态/作用域/幂等已测；多副本共享协调未实现 |
| 租户边界和 BFF 白名单 | 通过 | Repository 作用域、跨租户 404、逐项 BFF route |
| 生产安全配置 | 条件通过 | Fake/HTTP/空 key fail-fast；真实 Secret Manager/供应商审批未验证 |
| 自动化质量门禁 | 通过 | 35 tests + 13 subtests，89.76%，Ruff/Mypy/Next build |
| 依赖安全 | 通过（时点） | Python/npm 已知漏洞 0；无绕过下载完整性检查 |
| PostgreSQL/Compose 全栈 | 通过 | `20260715_0002`、OIDC+BFF+SSE+ledger smoke |
| Helm/Kubernetes 与性能 SLO | 未通过 | 本机无 Helm；无集群/Ingress/负载证据 |

## 2. 下一阶段授权范围

允许 S3 使用合成、公开或明确批准的非敏感测试资料实现：上传、对象存储、不可变文档版本、解析/切分、异步任务、ACL 元数据、Embedding Adapter 的 Fake/批准沙箱和索引原子发布。

S3 仍不得：

1. 将 confidential/restricted 文本发送到外部模型。
2. 在 ACL 生效前把 chunk 加入可搜索候选集合。
3. 用 Fake/合成指标宣称真实知识质量、成本或 SLO 达标。
4. 开放 Agent 写工具、真实客户数据或生产流量。
5. 绕过 R-S2-001 的共享配额/取消生产阻断。

## 3. 进入真实 Provider/staging 前的最小条件

- R-S2-001、002、004、006、009、010、012 有明确 Owner 和可复验证据。
- 企业 OIDC、Secret Manager、批准模型路由、DPA/区域与数据分级策略完成。
- Helm lint/集群安装、Ingress SSE、滚动发布、迁移/回滚和压测通过。
- 模型观测、预算告警、事故 Runbook 和 on-call 完成。

未满足这些条件时，本 Gate 的 “GO” 只表示继续开发，不表示上线许可。
