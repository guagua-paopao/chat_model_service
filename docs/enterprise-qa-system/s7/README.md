# S7：UAT、灰度发布与运营移交

S7 在 S6 本地工程基线上实现可运行的发布控制面：不可变候选清单、UC-01～05 UAT、五类独立签署、单调灰度、服务端自动停止/回滚、事件哈希链和只读运营控制台。

当前状态：`local_release_rehearsal_pass / production_no_go`。没有使用真实企业数据、真实镜像签名、真实 staging/production 流量或企业签字。

## 文档导航

1. [需求与范围](01-s7-requirements-and-scope.md)
2. [发布架构与不可变制品](02-release-architecture-and-artifact-evidence.md)
3. [UAT、审批与职责分离](03-uat-approval-and-separation-of-duties.md)
4. [灰度、门禁与回滚](04-progressive-rollout-gates-and-rollback.md)
5. [API、字段、数据与迁移](05-api-data-and-migration.md)
6. [部署、CI/CD 与供应链](06-deployment-cicd-and-supply-chain.md)
7. [运营培训与移交](07-operations-training-and-handover.md)
8. [开发教学与测试计划](08-development-tutorial-and-test-plan.md)
9. [验证报告](09-test-and-verification-report.md)
10. [S7 Gate](10-s7-gate-review.md)
11. [决策日志](11-decision-log.md)
12. [风险登记册](12-risk-register.md)
13. [机器可读清单](manifest.yaml)

## 本地验证

```powershell
.\scripts\check.ps1 -OnlineAudit
docker compose --env-file .env -f infra/compose/compose.yaml up -d --build
.\.venv\Scripts\python.exe scripts\smoke_s7.py
```

S7 发布写操作只用于 `local/test/dev`。目标环境必须接入批准的外部部署控制器，应用内本地编排器在 staging/production fail-closed。
