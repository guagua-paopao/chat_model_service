# Project Context

> 状态：S2 Model Gateway 与流式聊天纵切完成，生产条件待关闭  
> 基线版本：s2-v1.0  
> 基线日期：2026-07-15  
> 下一阶段：S3 文档上传与摄取流水线（仅合成/批准非敏感数据）

## 1. 当前目标

从零建设一套企业级大模型知识问答系统。首发验证范围固定为两个企业内部只读场景：

1. 员工制度问答：差旅、信息安全等受控制度。
2. IT 支持问答：账号、MFA、VPN、错误码和服务响应时限。

系统必须基于授权知识回答、提供引用、资料不足时拒答，并保留身份、租户、知识版本、检索、模型、耗时和成本的审计链路。

外部客户问答、Agent 工具写操作、多模态、复杂连接器和模型训练不属于首发范围。

## 2. 当前阶段状态

| 内容 | 状态 | 证据 |
|---|---|---|
| 项目范围与首发场景 | 工程基线已确定，待业务 Owner 签字 | `docs/enterprise-qa-system/s0/01-discovery-baseline.md` |
| 数据清单与分级策略 | 合成基线完成，真实数据盘点待输入 | `s0/02-data-inventory.md` |
| 黄金评测集 | 60 条合成样例完成，待业务双人复核 | `tests/evaluation/s0-golden-dataset.jsonl` |
| 架构与 ADR | ADR-001～018 已接受为开发基线 | `docs/enterprise-qa-system/adr/` |
| 威胁模型 | v0.1 完成，开发阶段持续更新 | `s0/05-threat-model.md` |
| 容量与成本 | 三档容量模型完成，真实价格/流量待确认 | `s0/06-capacity-and-cost-baseline.md` |
| 裸模型/RAG 基线实验 | 实验协议与记录模板完成，尚未运行真实模型 | `s0/04-baseline-experiment.md` |
| S0 Gate | 条件通过 | `s0/09-s0-gate-review.md` |
| S1 身份/租户/会话纵切 | 本地实现与全栈冒烟通过 | `s1/README.md` |
| S1 质量与供应链 | 21 tests + 9 subtests，89.66% coverage，Python/npm 漏洞 0 | `s1/05-test-and-verification-report.md` |
| S1 Gate | 条件通过 S2 合成开发；企业 OIDC、远端 dev 部署、Helm 集群验证待办 | `s1/07-s1-gate-review.md` |
| S2 Model Gateway/流式聊天 | Fake + OpenAI-compatible Adapter、SSE、取消/重试、用量成本已实现 | `s2/README.md` |
| S2 质量与供应链 | 35 tests + 13 subtests，89.76% coverage，Python/npm 已知漏洞 0 | `s2/05-test-and-verification-report.md` |
| S2 PostgreSQL/全栈 | migration `20260715_0002`，OIDC+BFF+SSE+账本 smoke 通过 | `s2/05-test-and-verification-report.md` |
| S2 Gate | 条件通过 S3 合成开发；共享配额/取消、真实模型、K8s/性能仍阻断生产 | `s2/07-s2-gate-review.md` |

## 3. 已接受技术基线

- Web：Next.js + TypeScript。
- API：Python 3.12 + FastAPI + Pydantic。
- 架构：模块化单体 + 独立异步 Worker，不在首版拆微服务。
- 数据：PostgreSQL + pgvector；Redis 用于队列/短期缓存；S3/MinIO 存原文件。
- 协议：REST + SSE；契约以 `openapi.yaml` 为准。
- 模型：通过统一 Model Gateway 连接至少两个 Adapter；领域层不依赖厂商 SDK。
- 部署：本地 Docker Compose；生产 Kubernetes + Helm。
- 观测：OpenTelemetry + Prometheus/Grafana + 集中日志/Trace。

## 4. 不可违反的约束

1. `tenant_id` 从可信认证上下文解析，客户端不得自报后直接使用。
2. 文档 ACL 必须在向量/关键词 top-k 召回前或安全候选集合中生效。
3. 只有当前已发布且未删除的文档版本可进入新问答。
4. Prompt、检索配置、模型路由和知识版本必须可追踪、可回滚。
5. 引用只能来自本次授权检索证据，打开原文时再次鉴权。
6. 无充分证据时拒答；系统故障、无资料与权限不可见必须使用不同内部原因、合适的安全外部文案。
7. 密钥不得进入 Git、数据库明文、客户端 bundle 或普通日志。
8. `confidential/restricted` 数据默认不得发送到外部云模型；只有经数据负责人批准的路由可以例外。
9. 首发只读问答，不开放业务写工具和无人审批的 Agent 行为。
10. AI 质量、安全、性能和成本门禁是发布条件，不以主观演示替代。

## 5. 当前质量门槛

- 检索 Recall@10 ≥ 0.85。
- Groundedness ≥ 0.90。
- 引用精确率 ≥ 0.90、完整率 ≥ 0.85。
- 无答案拒答 F1 ≥ 0.85。
- 成功跨租户/越权案例为 0。
- 基线流量下 TTFT P95 ≤ 2.5 秒，完整回答 P95 ≤ 15 秒。
- 生产月度可用性目标 99.9%，RPO ≤ 15 分钟、RTO ≤ 60 分钟。

以上门槛在真实业务集建立后允许通过正式变更流程校准，安全越权门槛不可降低。

## 6. 数据与模型默认政策

| 数据等级 | 外部批准云模型 | 企业私有模型 | 日志正文 |
|---|---:|---:|---:|
| public | 允许 | 允许 | 仍默认不记录完整正文 |
| internal | 仅批准供应商/区域 | 允许 | 默认不记录 |
| confidential | 默认禁止 | 允许 | 禁止 |
| restricted | 禁止 | 仅专用批准路由 | 禁止 |

模型请求不得用于供应商训练；正式接入前必须保存合同/数据处理条款和批准证据。

## 7. 当前开放问题

阻断真实数据/生产承诺但不阻断 S3 合成开发的问题：

- 真实业务 Owner、知识管理员、安全/法务和 SRE 的姓名与审批。
- 企业 OIDC issuer、组织/组映射和禁用传播时限。
- 真实文档规模、类型、密级、更新频率和 ACL 来源。
- 获批的 Chat/Embedding/Rerank 模型、区域、价格和数据条款。
- 峰值并发、月问题量、预算和最终保留期限。
- 真实黄金集的双人业务复核和基线实验结果。
- GitHub 主干到 dev 的真实部署环境、凭据、回滚和 smoke 证据。
- Helm lint、Kubernetes dev 安装、Secret/TLS/NetworkPolicy 与恢复演练。
- 多副本共享配额、并发租约与取消信号（当前仅进程内状态）。
- 目标环境 SSE 长连接、断线风暴、TTFT/完整耗时和 Provider 故障压测。

完整清单见 `docs/enterprise-qa-system/s0/08-open-questions.md`。

## 8. 下一步

1. 进入 S3 合成开发：安全上传、对象存储、不可变文档版本、解析/切分、异步状态机、ACL 元数据和原子索引发布。
2. Platform/API 完成 Redis 共享配额、并发租约和取消协调；在此之前禁止多副本生产。
3. 由用户/业务方回答 S0 开放问题；仅在批准后使用真实模型沙箱和非敏感资料运行基线实验。
4. Platform/IAM 并行补齐企业 OIDC、GitHub dev 自动部署、Helm/Kubernetes、Ingress SSE 和负载验证。
5. S3 PR 必须引用 ADR、OpenAPI、本文件约束和 `s2/07-s2-gate-review.md` 的禁止事项。

## 9. 规范优先级

发生冲突时依次采用：用户最新明确决定 → 已批准的变更/ADR → 本文件 → OpenAPI/数据库迁移等机器契约 → 专题设计文档 → 外部参考项目。任何改变安全边界、外部契约或数据政策的决定必须先更新 ADR 和本文件。
