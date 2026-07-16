# S6：质量、可观测性、韧性与恢复证据

S6 在 S5 企业治理基线上完成一套可运行的本地工程候选：版本化质量评测、基线差异门禁、隐私安全 OpenTelemetry、Prometheus/Grafana、SLO 告警骨架、有界压测、确定性故障注入和隔离恢复演练。

当前状态：`local_engineering_pass / production_no_go`。所有运行数据均为合成数据；没有使用真实企业文档或真实模型 Provider。

## 文档导航

1. [需求与范围](01-s6-requirements-and-scope.md)
2. [评测架构、数据集与门禁](02-evaluation-architecture-dataset-and-gates.md)
3. [可观测性、SLI/SLO、告警与 Runbook](03-observability-slo-alerts-and-runbooks.md)
4. [性能、容量与故障注入](04-performance-capacity-and-fault-injection.md)
5. [备份、恢复与灾难恢复](05-backup-recovery-and-dr.md)
6. [API、字段、数据与迁移](06-api-data-and-migration.md)
7. [开发教学与测试计划](07-development-tutorial-and-test-plan.md)
8. [验证报告](08-test-and-verification-report.md)
9. [S6 Gate 评审](09-s6-gate-review.md)
10. [决策日志](10-decision-log.md)
11. [风险登记册](11-risk-register.md)
12. [机器可读清单](manifest.yaml)

## 快速验证

```powershell
docker compose --env-file .env -f infra/compose/compose.yaml up -d --build
.\.venv\Scripts\python.exe scripts\smoke_s6.py
.\.venv\Scripts\python.exe scripts\fault_s6.py
.\.venv\Scripts\python.exe scripts\drill_s6_recovery.py
.\.venv\Scripts\python.exe scripts\load_s6.py --profile smoke --duration 3 --rps 2
```

本地入口：Web `http://127.0.0.1:3000`、API 文档 `http://127.0.0.1:8000/api/v1/docs`、Prometheus `http://127.0.0.1:9090`、Grafana `http://127.0.0.1:3001`。Grafana 匿名 Viewer 只适用于本地 Compose，生产必须接入企业 SSO/RBAC。
