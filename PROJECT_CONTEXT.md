# Project Context

> 状态：S6 本地工程 Gate 通过，真实数据/staging/production 仍为 NO-GO  
> 基线版本：s6-v1.0-local-candidate  
> 基线日期：2026-07-16  
> 下一阶段：关闭 S6 生产阻断项后进入 S7 UAT、灰度发布与运营移交

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
| 架构与 ADR | ADR-001～037 已接受为开发基线 | `docs/enterprise-qa-system/adr/` |
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
| S3 安全文档摄取 | 签名直传、双 bucket、四格式解析、异步 Worker、原子发布、ACL 前置调试检索已实现 | `s3/README.md` |
| S3 质量与全栈 | 45 tests，86% coverage；PostgreSQL/Redis/MinIO/OIDC/直传/Worker/检索 smoke 通过；Python/npm 已知漏洞 0 | `s3/05-test-and-verification-report.md` |
| S3 Gate | 条件通过 S4 合成 RAG 开发；真实数据、IAM/KMS/ClamAV/K8s/性能仍阻断生产 | `s3/07-s3-gate-review.md` |
| S4 RAG 闭环 | ACL-first hybrid/RRF/rerank、packing、grounded/search-only、拒答、引用再鉴权、反馈已实现 | `s4/README.md` |
| S4 质量与全栈 | 58 tests；20-case 合成指标均 1.0、泄漏 0；PostgreSQL pgvector/Compose smoke 通过 | `s4/05-test-and-verification-report.md` |
| S4 Gate | 条件通过 S5 合成质量/可观测性开发；真实数据/Provider/中文/性能/K8s/DR 仍阻断生产 | `s4/07-s4-gate-review.md` |
| S5 企业治理闭环 | 服务端目录态/group ACL、集中授权、配置门禁、DB 共享配额、哈希链、事件和控制台已实现 | `s5/README.md` |
| S5 质量与验证 | Python/契约/迁移/Web 证据见报告；本地 structural evaluator 不代表真实业务质量 | `s5/07-test-and-verification-report.md` |
| S5 Gate | 只条件通过 S6 合成/批准集成工作；生产仍 No-Go | `s5/08-s5-gate-review.md` |
| S6 质量与可靠性 | 不可变评测运行、基线差异门禁、低基数 OTel、Prometheus/Grafana、SLO 告警、有界负载、故障和恢复工具已实现 | `s6/README.md` |
| S6 质量与验证 | 72 tests + 35 subtests，88.84% coverage；Python/npm 已知漏洞 0；全栈 smoke、5 个故障场景、4 个恢复不变量通过 | `s6/08-test-and-verification-report.md` |
| S6 Gate | 本地工程 PASS；合成/批准范围 CONDITIONAL GO；真实数据、staging、production NO-GO | `s6/09-s6-gate-review.md` |

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

阻断真实数据、staging 和生产承诺，但不阻断 S6 合成/公开/逐项批准范围维护的问题：

- 真实业务 Owner、知识管理员、安全/法务和 SRE 的姓名与审批。
- 企业 OIDC issuer、组织/组映射和禁用传播时限。
- 真实文档规模、类型、密级、更新频率和 ACL 来源。
- 获批的 Chat/Embedding/Rerank 模型、区域、价格和数据条款。
- 峰值并发、月问题量、预算和最终保留期限。
- 真实黄金集的双人业务复核和基线实验结果。
- GitHub 主干到 dev 的真实部署环境、凭据、回滚和 smoke 证据。
- Helm lint、Kubernetes dev 安装、Secret/TLS/NetworkPolicy 与恢复演练。
- 跨实例取消信号仍是进程内；速率/并发配额已改为数据库共享窗口和 TTL 租约，但待 PostgreSQL 压测。
- 目标环境 SSE 长连接、断线风暴、TTFT/完整耗时和 Provider 故障压测。

完整清单见 `docs/enterprise-qa-system/s0/08-open-questions.md`。

## 8. 下一步

1. 由 Product/Business/Data/Security 完成真实黄金集、holdout、claim verifier、红队方案和具名签字；不得复用 24 条合成结构评测作为业务质量证明。
2. 将同步本地评测器替换为批准的异步 Worker，补齐队列幂等、超时、取消、重试和受控数据存储。
3. Platform/IAM 接入企业 OIDC/SCIM、Secret/TLS/NetworkPolicy/Ingress，并完成目标集群 50 RPS、200 SSE、24 小时 soak 与故障切换。
4. SRE/DBA 接入 Alertmanager/Pager、Trace/日志后端，完成 PostgreSQL PITR、对象版本与多区域隔离恢复演练。
5. 只有 S6 Gate 阻断项关闭并完成具名签字后才能进入 S7；任何真实数据、外部 Provider、企业系统写入或公开发布均须单独授权。

## S6 当前基线（覆盖文首旧阶段状态）

- 当前版本：`s6-v1.0-local-candidate`，日期 2026-07-16；证据包：`docs/enterprise-qa-system/s6/`。
- 已完成：0007 不可变评测运行、24 条合成固定集、基线差异门禁、usage/operations API、W3C Trace Context、低基数 OTel、Prometheus/Grafana、4 条带 Owner/Runbook 告警、有界负载、5 个 Fake Provider 故障场景和隔离恢复演练。
- 验证证据：72 tests + 35 subtests、88.84% coverage；Ruff/mypy/ESLint/TypeScript/Next build 通过；Python/npm 已知漏洞 0；10 个 Compose 长期服务在线。
- ADR 基线：ADR-001 至 ADR-043；S6 新增 ADR-038 至 ADR-043。
- 关键限制：本机小样本不是容量证明，SQLite/本地目录恢复不是 PostgreSQL PITR/跨区域 DR，合成结构评测不代表真实业务质量，Prometheus 骨架未接企业 Pager/日志/Trace 后端。
- Gate：本地工程 PASS；只允许合成、公开或逐项批准非敏感范围继续；真实数据、staging、production 仍 NO-GO；S6 上传 GitHub 需用户另行明确确认。

## 12. S5 当前基线（覆盖文首旧阶段状态）

- 当前版本：`s5-v1.0-local-candidate`，日期 2026-07-16；证据包：`docs/enterprise-qa-system/s5/`。
- 已完成：服务端 user/role/group 解析、集中 PolicyEngine、group ACL-first、用户立即停权、配置 draft/evaluate/独立 approve/publish/immutable rollback、数据库共享 quota window/lease、治理 hash chain、安全事件状态机、用量/质量摘要、Web `/admin`、0005/0006 migrations 和 S5 smoke。
- ADR 基线：ADR-001 至 ADR-037；S5 新增 ADR-033 至 ADR-037。
- 关键限制：local evaluator 仅结构/安全预检且在 staging/production 被禁止；哈希链未外送 WORM；真实企业 IdP/SCIM 和签字缺失；取消仍进程内；无目标 Prometheus/告警/K8s/性能/DR 证据。
- Gate：只授权 S6 在合成、公开或逐项批准范围补生产化证据；S5 完整公开发布仍需用户另行明确确认。

## 11. S4 当前基线（覆盖文首旧阶段状态）

- 当前版本：`s4-v1.0`，日期 2026-07-16；证据包：`docs/enterprise-qa-system/s4/`。
- 已完成：ACL-first pgvector/FTS、weighted RRF、Fake/HTTPS Reranker、context packing、evidence gate、grounded output buffer、Source ID 验证、search-only/no-model abstention、immutable citation/current ACL、feedback、Web/BFF、0004 migration、Compose/Helm 参数。
- 质量证据：58 tests；`s4-mini-golden-v1` 20 cases 的 Recall@10、citation precision/completeness、groundedness proxy、abstention precision/recall 均 1.0，unauthorized leakage 0。
- ADR 基线：ADR-001 至 ADR-032；S4 新增 ADR-025 至 ADR-032。
- 生产阻断：真实业务评测/claim verifier、企业 IAM、真实 Provider/数据条款、中文 tokenizer、固定维度 ANN benchmark、red-team/sandbox、共享 Redis、S3/ClamAV 生产控制、Kubernetes/Ingress/Secret/NetworkPolicy、SLO/观测/DR。
- 下一阶段：只允许 S5 合成/批准范围开发；S4 完整公开发布仍需用户另行明确确认。

## 9. 规范优先级

发生冲突时依次采用：用户最新明确决定 → 已批准的变更/ADR → 本文件 → OpenAPI/数据库迁移等机器契约 → 专题设计文档 → 外部参考项目。任何改变安全边界、外部契约或数据政策的决定必须先更新 ADR 和本文件。

## 10. S3 当前基线（覆盖文首旧阶段状态）

- 当前版本：`s3-v1.0`，日期 2026-07-16；证据包：`docs/enterprise-qa-system/s3/`。
- 已完成：签名直传、quarantine/published、不可变文档版本、四格式解析、结构分块、Fake/外部 Embedding Adapter、DB lease Worker、重试/dead-letter、原子 chunk 发布、user/role ACL 前置调试检索、Web 状态/错误、Compose/Helm/迁移/OpenAPI。
- 当前 Gate：仅允许 S4 使用合成、公开或批准非敏感资料开发 hybrid retrieval、引用和拒答；聊天仍不连接知识检索。
- ADR 基线：ADR-001 至 ADR-024。新增 ADR-019 至 ADR-024 约束对象边界、原子发布、任务租约、ACL 顺序、provenance 和生产 fail-fast。
- 生产阻断：真实数据审批、企业 group/SCIM、ClamAV/解析沙箱、S3 IAM/KMS/lifecycle/reconciliation、真实 Embedding/Model、真实文档 UAT、多 Worker 压测、共享 Redis、Kubernetes/Ingress/NetworkPolicy/Secret、性能/观测/DR。
- 下一阶段：S4 RAG 闭环；不得把 S3 debug lexical score 或 Fake Embedding 当生产质量证据。
