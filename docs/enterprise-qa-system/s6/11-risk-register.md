# S6 风险登记册

| ID | 风险 | 可能性/影响 | 当前控制 | Owner | 关闭条件 |
|---|---|---|---|---|---|
| S6-R01 | 合成评测被误当真实业务质量 | 高/高 | manifest/Gate/响应明确范围 | AI Quality | 批准黄金集与业务签字 |
| S6-R02 | 同步评测阻塞 API | 中/高 | 仅 local；生产 fail-closed | Platform | 外部异步 Worker 压测通过 |
| S6-R03 | 指标高基数或泄露 | 中/高 | 白名单标签、路由模板、测试 | SRE/Security | 目标后端基数/隐私审计 |
| S6-R04 | OTel/Collector 故障拖累业务 | 低/高 | Batch export、业务与导出分离 | SRE | 目标环境 Collector failure drill |
| S6-R05 | 告警表达式正确但路由无效 | 高/高 | promtool + Runbook | SRE | Pager 实际触发/恢复演练 |
| S6-R06 | 开发机负载结果被外推 | 高/高 | 输出 production=false | QA/SRE | 目标集群 load/soak 证据 |
| S6-R07 | 压测误打外部环境 | 低/高 | localhost 默认、硬上限 | QA | 变更审批和网络 allowlist |
| S6-R08 | Fake Provider 行为不同于真实供应商 | 高/高 | 明确合成范围 | Model Platform | 真实 429/timeout/stream drill |
| S6-R09 | 本地恢复不代表 PITR | 高/高 | Gate 维持 No-Go | DBA/SRE | 隔离 PostgreSQL/object restore |
| S6-R10 | Grafana 匿名访问被误部署 | 中/高 | 仅 Compose loopback、Helm 不部署 Grafana | Security | 企业 SSO/RBAC 验收 |
| S6-R11 | 评测快照含敏感 prompt | 中/中 | tenant scope、API 不返回 snapshot | Data/Security | 加密、保留期和访问审计 |
| S6-R12 | 用量聚合与供应商账单不一致 | 中/中 | append-only ledger/estimated 标记 | FinOps | 月度 reconciliation |
| S6-R13 | 历史 Postgres 卷密码漂移 | 中/中 | 保留卷、受控角色对齐后迁移 | Dev Platform | Secret 生命周期和本地 runbook |
| S6-R14 | 生产目标未由 Owner 签字 | 高/高 | 标记为假设，生产 No-Go | Product/SRE | 正式 NFR 签字 |
