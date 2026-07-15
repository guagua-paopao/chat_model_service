# 09. 部署与 CI/CD

## 1. 环境拓扑

### 1.1 本地 Compose

服务：`web, api, worker, scheduler, postgres(pgvector), redis, minio, otel-collector`。可选 `prometheus/grafana/tempo/loki` 作为完整观测 profile。所有镜像固定版本或 digest，不使用 `latest`。

开发配置使用 `.env.example` 列出名称和无密示例；真实 secret 放本机 secret store/受忽略文件。种子脚本创建两个租户、多个角色和公开/受限文档，用于跨租户负向测试。

### 1.2 企业环境

| 环境 | 隔离 | 数据 | 模型 | 目的 |
|---|---|---|---|---|
| dev | 独立 namespace/账号 | 合成 | Fake/开发额度 | 合并验证 |
| test | 独立账号/VPC 优先 | 合成/批准脱敏 | Fake+沙箱 | 系统/性能/安全 |
| staging | 生产同构 | 批准脱敏 | 生产同类低额度 | UAT/发布演练 |
| prod | 独立生产账号/VPC | 真实 | 批准生产路由 | 正式服务 |

生产和非生产使用不同数据库、桶、Redis、KMS/Secret、OIDC client 和模型 key。禁止网络或凭证允许非生产应用访问生产数据面。

## 2. Kubernetes 工作负载

| Workload | 形态 | 扩缩指标 | 说明 |
|---|---|---|---|
| Web | Deployment | CPU/RPS | 静态资源优先 CDN；无状态 |
| API | Deployment | CPU、RPS、活动 SSE、延迟 | readiness 不把可降级供应商作为硬依赖 |
| Ingestion Worker | Deployment | queue depth/oldest age | parse/embed 分队列和并发池 |
| Eval Worker | Deployment/Job | queue depth | 与在线资源隔离，低优先级 |
| Scheduler/Outbox | Deployment（leader election） | 单活/小副本 | 防止重复调度，任务仍需幂等 |
| Migration | 独立 Job | 不扩缩 | 应用 rollout 前受控执行 |

生产基线：至少 2–3 个 API 副本跨可用区；Pod anti-affinity/topology spread；PDB；requests/limits；startup/readiness/liveness；非 root、只读根目录、drop capabilities、seccomp；独立 ServiceAccount 和 NetworkPolicy。

健康检查语义：

- `/health/live` 只证明进程事件循环可用，失败才重启。
- `/health/ready` 检查接受流量的必要内部依赖（如 DB）；可降级的模型供应商不应让所有 Pod 永久 unready。
- startup probe 给迁移后预热/模型 tokenizer 加载足够时间，避免 liveness 重启循环。

## 3. 配置矩阵

| 类别 | 示例 | 存放 | 是否动态 |
|---|---|---|---:|
| 非密运行配置 | log level、port、OTel endpoint | ConfigMap/部署值 | 部分 |
| 连接信息 | DB host、Redis endpoint、bucket | Secret/配置引用 | 否/滚动 |
| 凭证 | DB password、model key、OIDC secret | Secret Manager + workload identity | 可轮换 |
| 业务配置 | Prompt、检索、模型路由、配额 | DB 不可变版本 | 发布切换 |
| Feature flag | 渠道/灰度/模型候选 | 受审计 flag 服务/DB | 是 |

不得把 Prompt、模型选择和关键安全策略散落在 Helm values 与环境变量中；它们需要版本、审批、评测和回滚。

## 4. CI 流水线

PR 流水线建议顺序：

1. 变更范围、commit/PR 元数据与生成文件检查。
2. 格式、lint、类型、OpenAPI/SQL/Helm lint。
3. 单元测试与覆盖率。
4. Testcontainers 集成：PostgreSQL/pgvector、Redis、S3、Fake Provider。
5. Web E2E 核心路径。
6. SAST、secret scanning、SCA、许可证、IaC 与容器扫描。
7. 构建一次不可变 Web/API/Worker 镜像，生成 SBOM、provenance 并签名。
8. 若影响 RAG/Prompt/Parser/Model，运行快速质量集。
9. 生成合并报告；硬门禁未通过不可合并。

对 fork/untrusted PR 禁止注入生产或高权限 secret，避免 CI 脚本窃取凭证。

## 5. CD 与发布制品

同一 image digest 从 dev 晋升到 staging/prod，不为环境重新 build。Release manifest 示例：

```yaml
release_id: qa-2026.07.15.1
git_sha: 2b6d...
images:
  api: registry.example.com/qa-api@sha256:...
  web: registry.example.com/qa-web@sha256:...
  worker: registry.example.com/qa-worker@sha256:...
db_migration: '2026071501'
contracts:
  openapi_sha256: '...'
configs:
  prompt_versions: [pv_17]
  retrieval_versions: [rv_7]
  model_route_versions: [mv_12]
quality:
  dataset_version: '2026.07.1'
  evaluation_run_id: 'eval_...'
approvals: [product, engineering, qa, sre, security]
```

CD 流程：部署基础兼容变更 → migration expand → 部署新应用 → smoke/contract → 灰度 → 指标与质量判定 → 全量 → 后续 contract cleanup。生产部署由受保护环境审批，部署身份只有目标 namespace/资源所需权限。

## 6. 数据库迁移

- 迁移由独立 Job/受控工具执行，应用 Pod 不在启动时争抢迁移锁。
- Expand：新增表/可空列/兼容索引；旧应用仍可运行。
- Migrate：后台分批回填，限速，监控复制延迟、锁、WAL/日志和失败。
- Switch：新应用双写/新读，校验一致性。
- Contract：经过至少一个稳定发布和回滚窗口后删除旧字段。
- 大索引并发创建；DDL 前估算锁与磁盘。不可逆变更提供前向修复和恢复快照。

每个迁移 PR 附：数据量假设、预计时间、锁风险、兼容矩阵、校验 SQL、停止条件、回滚/前向修复。向量模型/维度变化采用影子索引重建，完成评测后原子切换配置。

## 7. 灰度与回滚

### 7.1 放量

内部测试租户/暗流量 → 5% → 25% → 50% → 100%。模型/Prompt/检索配置也作为独立可灰度发布物，按 tenant/user hash 稳定分桶，避免同一会话中途切换。

每档比较：平台 5xx、TTFT/完整延迟、Provider/fallback、SSE 中断、检索空结果、拒答、引用、负反馈、安全事件、token/成本、资源和队列。指标超过阈值自动暂停，P0/P1 自动回滚/关闭功能。

### 7.2 回滚层级

| 层级 | 动作 | 目标时间 |
|---|---|---:|
| Feature | 关闭新渠道/缓存/reranker/连接器 | 5 分钟 |
| Config | 切回 Prompt/检索/模型路由旧版本 | 5–10 分钟 |
| App | Helm/平台回滚到旧 image digest | 15 分钟 |
| Data | 前向修复/恢复/重建影子索引 | 按 RTO |

应用回滚必须兼容 expand 后数据库；不要依赖生产中运行破坏性 down migration。若数据已经由新代码写入，回滚前检查旧代码能否理解。

## 8. Secret 与证书发布

- 使用 workload identity 获取 secret，避免长生命周期静态凭证。
- Secret 更新支持双版本：应用接受新旧 → 更新使用方 → 撤销旧值 → 验证告警。
- 轮换模型 key、OIDC client、DB/Redis/S3 凭证和 Webhook HMAC，有日历、Owner 和演练。
- TLS 证书自动续期并监控剩余期限；严禁为了排障关闭证书验证。

## 9. 备份与恢复

| 资产 | 备份/恢复策略 | 验证 |
|---|---|---|
| PostgreSQL | 连续归档/PITR + 日快照，跨故障域复制 | 月度恢复到隔离环境、数据校验 |
| 对象存储 | 版本控制/不可变策略（按需）、生命周期、跨区副本 | 抽样恢复 hash/权限 |
| Redis | 视为可重建缓存；队列任务以 DB 状态/outbox 为真相 | 丢失后重放/重建 |
| 向量索引 | 数据库备份或由原文+配置重建 | 抽样召回/全量重建演练 |
| 配置/Prompt | DB 版本 + release manifest | 指定 release 可恢复 |
| IaC/Helm | Git + 制品库 | 空环境重建演练 |
| Secret | 企业密钥备份/灾备流程 | 受控 break-glass 演练 |

默认目标 RPO 15 分钟、RTO 60 分钟；业务确认后调整。恢复测试必须验证租户隔离、ACL、知识版本、引用和审计，不只看数据库能启动。

## 10. 生产上线清单摘要

- 域名、TLS、WAF、OIDC、CORS/CSP、限流、出网 allowlist 已验证。
- Pod 资源、HPA、PDB、spread、NetworkPolicy、ServiceAccount 和优雅终止已测试。
- 数据库容量、连接池、索引、备份、PITR、迁移与回滚演练通过。
- Secret 无明文，轮换/吊销/审计可用；镜像固定 digest、签名和 SBOM 完成。
- SLO 仪表盘/告警/Runbook/on-call 生效；成本预算和 Provider 配额告警已测试。
- 质量、安全、性能、UAT 与开源许可报告批准；发布/关停/恢复负责人在线。

## 11. 版本与升级策略

- 应用使用 SemVer/日期 release 均可，但 API、DB、配置和知识版本必须独立追踪。
- 每月至少进行依赖/基础镜像例行升级；高危漏洞按安全 SLA 加急。
- Kubernetes、PostgreSQL、pgvector、Redis 和解析工具升级先在恢复出的 staging 数据副本验证。
- 模型提供方可能在同名模型下变化：尽量固定版本，监控公告；任何模型切换按配置候选发布并跑回归。
- 维护兼容矩阵和 EOL 日历，禁止长期依赖无支持版本。

