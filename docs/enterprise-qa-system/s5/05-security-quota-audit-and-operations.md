# S5 安全、配额、审计与运维设计

## 1. 威胁与控制

| 威胁 | 入口 | S5 控制 | 剩余风险/生产要求 |
|---|---|---|---|
| 伪造角色/组 | JWT/request | 只从 DB 目录态解析 | 企业 IdP/SCIM 未接入 |
| 陈旧停权 | 长寿命 token/cache | 每请求检查 user status | 高 QPS 后缓存需失效证明 |
| 跨租户管理 | guessed UUID | Principal tenant + SQL tenant 条件 | 需真实渗透/RLS 验证 |
| 创建人自批 | 配置 API | 专用 permission + creator!=approver | 外部审批号真实性未校验 |
| 客户端伪造评测 | evaluation API | server-owned dataset/evaluator | local evaluator 不是业务质量 |
| 回滚重写历史 | config status | 新 immutable clone | 并发发布需 PostgreSQL 压测 |
| 多实例配额放大 | 独立计数 | tenant DB lock/window/lease | tenant 热点、取消仍本地 |
| 租约泄漏 | 进程崩溃 | expires TTL + acquire 清理 | scheduler 物理清理/告警待接 |
| 审计行修改 | DB 写权限 | sequence/hash verification | DBA 可重写全链，需 WORM |
| 日志泄密 | request/error/audit | 白名单字段、no body/token | 目标 APM/SIEM 仍需扫描 |
| 高基数观测 | tenant/user/query label | tenant-scoped API 聚合、无正文 | Prometheus/Grafana 未接 |
| 事件证据泄密 | title/resolution | 只存 safe refs/摘要 | 培训/DLP/工单集成待办 |

## 2. OWASP GenAI 风险映射（工程参考，不是认证）

| 风险主题 | 控制 |
|---|---|
| Prompt Injection | SOURCE 不可信边界、注入片段清洗、安全 query 拒答、配置门禁、事件分类 |
| Sensitive Information Disclosure | 分类路由、日志白名单、引用再鉴权、无 raw Prompt 审计、secret 扫描 |
| Supply Chain | 依赖 lock、pip/npm audit、gitleaks、镜像构建；签名/SBOM 发布平台待接 |
| Data/Model Poisoning | immutable 文档/config、provenance、审批、评测；真实数据质量签字待办 |
| Improper Output Handling | grounded buffer + citation validation、Web 默认转义 |
| Excessive Agency | 首发只读，无业务写工具/无人审批 Agent |
| System Prompt Leakage | unsafe query pattern、Prompt 条款、日志/审计不保存 Prompt |
| Vector/Embedding Weakness | ACL-first、当前 ACL 引用再鉴权、semantic cache 禁用 |
| Misinformation | evidence gate、拒答、引用、反馈和质量摘要 |
| Unbounded Consumption | 请求/并发/token/cost quota、model gateway timeout/retry bound |

正式安全评审须以组织采用的 OWASP GenAI/ASVS 版本、监管和内部控制库为准。

## 3. 配额准入算法

```text
estimate input tokens; reject oversized
BEGIN
  SELECT tenant FOR UPDATE
  resolve user override else tenant policy else fail-safe defaults
  reject disabled policy
  delete expired leases
  count tenant/user active leases; enforce limits
  lock/create current user-minute window; enforce request rate
  sum today's settled tokens, active token leases, and month's settled cost
  enforce daily token reservation and monthly settled-cost limits
  increment window + reserve estimated input
  insert lease(input_tokens_reserved, expires = now + model_total_timeout + 30s)
COMMIT
execute chat
finally DELETE lease
```

失败策略：数据库/策略不可用不退回内存计数；请求失败并触发基础设施告警。配额窗口增量在后续业务失败时不回退，防止攻击者用失败请求绕过速率。活动 lease 保存 input token 预留，日限额按已完成 ledger + 全部未过期预留 + 本次估算检查，终态删除、崩溃由 TTL 释放。月成本当前只按 Provider 已结算 ledger 拦截，仍可能超出一个并发批次；生产硬成本上限必须加入按路由价格的最大费用预授权和终态 reconcile。

## 4. 哈希链验证与响应

完整性验证失败：

1. 立即将该租户治理写操作切为只读/维护模式（S5 未实现自动开关，按 Runbook 人工执行）。
2. 保存数据库快照，不修复或删除可疑行。
3. 对比 WORM/SIEM 外部副本、数据库审计和备份；确定 first_invalid_sequence。
4. 创建 P0/P1 事件并通知 Security/DBA/Audit/Data Owner。
5. 只有在批准的取证/恢复方案后重建链；原链和调查证据永久保留。

本地测试通过直接修改 first event reason 验证 `valid=false`。这只证明检测算法，不证明生产不可抵赖。

## 5. 日志/审计字段白名单

允许：request_id、trace_id、tenant internal ID、actor internal ID、动作、resource internal ID、状态/版本、checksum、evaluation/report ID、稳定错误码、聚合计数、耗时。

禁止：Authorization/cookie/JWT、API key/secret、raw Prompt/query/answer、文档正文/quote、完整请求体、用户邮箱/姓名（除受控用户管理响应）、外部工单正文、对象存储签名 URL。

## 6. 观测指标与告警设计

目标平台应从结构化日志/OTel 生成低基数指标；tenant/user 只进入受控日志属性或租户内 API，不进入全局 metric label。

| Signal | 建议窗口/阈值 | Severity | Runbook |
|---|---|---:|---|
| auth denied 突增 | 5m > 基线 3σ | P2 | 检查 IdP/目录同步/攻击 |
| disabled propagation lag | P95 > 5m | P1 | 停止 IAM 变更发布 |
| config gate failed | 任一 publish candidate | P2 | 检查 failed_checks/report |
| publish without approval | 必须为 0 | P0 | 冻结配置写入/取证 |
| audit integrity invalid | 任一 tenant | P0 | 执行哈希链事件 Runbook |
| quota DB errors | 5m > 0.5% | P1 | DB/锁/连接池；fail closed |
| quota reject rate | 10m > 5% | P2/FinOps | 滥用或容量不足 |
| lease oldest age | > total timeout + 60s | P2 | 清理/崩溃恢复 |
| abstention rate | 1h 超 baseline + 20pp | P2 | 知识/检索/config 回退 |
| negative feedback | 1h > 10% 且样本≥30 | P2 | 质量分析 |
| P0/P1 open incident | 任一 | P0/P1 | 阻断 Gate |

## 7. 运行手册

### 配置发布失败

- 读取 evaluation dataset/evaluator/checksum 和 failed_checks；不直接改 DB 状态。
- 修复后创建新 draft 或对 evaluated draft 重跑；不要覆盖旧 evidence。
- 发布后观察 config version 分解的拒答、引用、成本、延迟；S5 UI 尚未提供版本分解，目标平台必须补。

### 配额大量 429

- 区分 rate/concurrency/daily/monthly code；确认是否单用户攻击、租户增长或卡住 lease。
- 检查 DB lock wait 和 quota_leases expires；不要直接把所有限额调大。
- 变更必须 ETag + reason + FinOps approval；完成后验证治理 hash chain。

### 用户已停权仍访问

- 确认请求命中的 tenant/issuer/subject、DB user status、应用是否使用旧缓存/旧版本。
- 若真实 IdP 未同步，禁用应用 DB 用户并撤销 IdP session/token；记录事件。
- 检查 group/role valid_until 和所有 API 副本版本；生产要求五分钟 SLA 证据。

### 配置质量回退

- 若存在已验证历史版本，使用 rollback API 创建新版本；不得 UPDATE 旧行。
- 记录 incident、approval_id、reason；观察窗口内禁止其他配置发布。
- 保留 current/target/new clone checksum 和评测/反馈证据。

## 8. 安全事件升级

| Severity | 示例 | 目标响应 |
|---|---|---|
| P0 | 跨租户泄露、审计链被破坏、生产密钥外泄 | 立即遏制/停写/高管与法务升级 |
| P1 | 可利用权限绕过、停权严重超 SLA、广泛错误回答 | 15 分钟响应，阻断发布 |
| P2 | 合成攻击触发、局部质量/配额异常 | 工作时段快速处置 |
| P3 | 无影响的观察/改进项 | 进入 backlog |

具体 SLA、联系人和法定义务必须由企业事件响应计划填写；本仓库不虚构人员。
