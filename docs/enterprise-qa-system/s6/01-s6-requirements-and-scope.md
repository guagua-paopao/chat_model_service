# S6 需求与范围

## 1. 目标

让团队能够回答四个企业发布问题：候选配置是否比基线差、服务是否在目标 SLO 内、依赖故障是否被隔离、备份是否真的可恢复。

## 2. 应用场景

| 场景 | Actor | 输入 | 系统行为 | 验收 |
|---|---|---|---|---|
| 发布候选评测 | Governance Admin | 数据集版本、1–5 个配置、可选基线 | 固化快照并运行门禁 | 可复现、租户隔离、失败阻断 |
| 评测审计 | Auditor/Approver | run id 或列表过滤 | 只读返回指标、阈值、差异和安全 case ID | 无原始问答泄露 |
| 运行排障 | SRE/Auditor | 当前租户和进程窗口 | 返回低基数请求与数据库信号 | 明确非生产 SLO 证据 |
| 成本分析 | FinOps/Auditor | 最长 31 天窗口、分组 | 从追加式账本聚合 | 不返回正文和用户标签 |
| 告警处理 | On-call | Prometheus 告警 | 按 Owner/Runbook 定位与缓解 | 告警可触发、可恢复、可复盘 |
| 恢复演练 | SRE/DBA | 备份集 | 隔离恢复并验证不变量 | RPO/RTO 与数据校验有证据 |

## 3. 功能范围

- `POST/GET /api/v1/evaluations/runs` 与单次读取。
- 数据集 SHA-256、候选配置快照、基线差异、质量门禁、治理审计。
- `GET /api/v1/usage` 和 `GET /api/v1/admin/operations/snapshot`。
- 手工 W3C Trace Context、OTLP gRPC 导出、HTTP/评测指标。
- OTel Collector → Prometheus → Grafana 本地链路；4 条带 Owner/Runbook 的告警。
- API/SSE 有界压测、Fake Provider 故障注入、SQLite+对象隔离恢复演练。
- Alembic `20260716_0007`、OpenAPI `1.6.0-s6`、Helm/Compose/Web 更新。

## 4. 非功能基线

| 指标 | 假设目标 | S6 本地结论 |
|---|---:|---|
| 月可用性 | 99.9% | 指标/告警已建；无生产窗口证据 |
| TTFT P95 | ≤ 2.5 s | SSE 工具已建；无真实 Provider 证据 |
| 完整回答 P95 | ≤ 15 s | 工具已建；无真实 Provider 证据 |
| API 基线吞吐 | 50 RPS | 未在目标集群验证 |
| SSE 并发 | 200 | 未在目标 Ingress 验证 |
| RPO | ≤ 15 min | 本地合成演练通过；无生产 PITR 证据 |
| RTO | ≤ 60 min | 本地合成演练通过；无生产切换证据 |
| 越权泄露 | 0 | 自动化回归继续通过 |

## 5. 明确不在范围

- 真实企业黄金集、人工双人标注、LLM-as-judge 校准和红队签字。
- 真实 Provider、真实企业 IAM/SIEM/Pager、生产数据库/对象存储操作。
- 在未批准的外部环境发起压测或故障注入。
- 自动生产发布、自动回滚、财务结算和多区域流量切换。

## 6. 完成定义

本地工程完成要求：代码/契约/迁移/测试通过；全栈 10 个长期服务运行；Prometheus target up；告警通过 promtool；S6 smoke、故障、恢复和短时压测通过；ADR、风险、Gate 和验证报告归档。生产完成定义仍需关闭 [Gate 阻断项](09-s6-gate-review.md)。
