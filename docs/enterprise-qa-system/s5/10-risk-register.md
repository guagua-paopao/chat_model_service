# S5 风险登记

> 状态定义：`blocked` 阻断真实数据/生产；`open` 需在后续阶段验证；`accepted-local` 只接受本地合成环境残余风险。

| ID | 严重度 | 风险与当前证据 | 状态 | Owner 角色 | 缓解措施 | 关闭条件 |
|---|---:|---|---|---|---|---|
| S5-R01 | P1 | 只有 Fake OIDC 和本地目录，无企业 SCIM、组源或离职传播 SLA | blocked | IAM Owner | 对接企业 IdP；同步/重放/乱序/停权演练 | IAM 报告批准，禁用 P95/P99 达标 |
| S5-R02 | P1 | local evaluator 只做结构/安全 fixture，无法证明业务质量 | blocked | AI Quality Owner | 独立 Worker、批准多语言集、holdout、签名报告 | 质量与红队 Gate 由独立审批人签字 |
| S5-R03 | P1 | hash chain 与业务数据同库，DB 管理者可重算 | blocked | Audit/Security | 异步可靠外送 SIEM/WORM、周期锚定和对账 | 篡改/丢包演练和留存策略批准 |
| S5-R04 | P1 | 无目标环境 OWASP GenAI 红队和 P0/P1 安全签字 | blocked | Security Owner | 注入、泄漏、投毒、过度授权、资源耗尽测试 | 未缓解 P0/P1 为 0 |
| S5-R05 | P1 | 无 Kubernetes、secret manager、NetworkPolicy、真实 TLS/Ingress | blocked | Platform/SRE | staging 部署和平台控制验证 | 平台检查、渗透与变更评审通过 |
| S5-R06 | P1 | 无备份恢复、PITR、对象一致性和 RPO/RTO 演练 | blocked | DBA/SRE | 隔离恢复和故障演练 | 实测 RPO/RTO 达标且签字 |
| S5-R07 | P2 | PostgreSQL 配额按 tenant 串行，热点租户可能锁等待或死锁 | open | API/DBA | 目标并发 benchmark、超时/重试指标；必要时 Redis 原子实现 | 2 倍峰值满足 SLO，无错误计费 |
| S5-R08 | P2 | 并发取消仍为进程内状态，其他实例不能立即取消 | open | API Owner | 共享 cancel token/pub-sub，断连与 crash 演练 | 跨实例取消和恢复测试通过 |
| S5-R09 | P2 | 配额未覆盖 service account、上传容量和摄取队列；月成本仅按已结算 ledger，可能超出一个并发批次 | open | Product/API | 扩展 scope/ledger/enforcement；增加路由最大费用预授权和终态 reconcile | 所有 Must 配额矩阵、硬成本边界与对账通过 |
| S5-R10 | P2 | 管理列表为教学规模，分页/目录大规模基准不完整 | open | API/IAM | 游标分页、组合索引、50k 用户/组基准 | P95/P99 和 DB 计划批准 |
| S5-R11 | P2 | 管理 Web 只有只读控制台；写入流程没有 CSRF/二次确认 UX | accepted-local | Web/Security | 写操作保持 API；上线前实现 CSRF、确认和审计预览 | Web 安全评审与端到端测试通过 |
| S5-R12 | P2 | 事件响应是台账，不会自动分页、封禁或证据保全 | open | SOC/SRE | 对接告警/工单/pager 与 Runbook | P0/P1 演练达到响应时限 |
| S5-R13 | P2 | Python lock 未含 hash；无 SBOM、镜像签名和 gitleaks 本机证据 | blocked | Supply Chain | hashed lock、SBOM、签名、registry/secret/license gate | CI 制品证明和 0 高危策略通过 |
| S5-R14 | P2 | Compose Fake Provider 证据不能代表真实上游数据处理和故障语义 | blocked | AI Platform/Data | 供应商 DPA、分类路由、429/timeout/账单对账 | Provider 审批和 staging 故障报告通过 |
| S5-R15 | P2 | 真实 dashboard、alert、低基数指标和 on-call 尚未接入 | open | Observability/SRE | S6 接入指标、告警、Runbook 与抑制 | 每条告警触发并由 Owner 演练 |
| S5-R16 | P3 | 本地 Fake persona 与默认种子可能被误用于非本地环境 | accepted-local | Platform | production validation 禁用本地 evaluator/Fake Provider；部署审查 | staging 启动负向测试与配置策略通过 |

## 风险处理纪律

- `blocked` 项未关闭前，不得把 S5 标记为 production ready。
- 关闭必须附日期、环境、命令/报告、具名 Owner 和批准人；仅提交代码不等于关闭。
- 风险降级必须有可验证的新控制或概率/影响数据，不能只改标签。
