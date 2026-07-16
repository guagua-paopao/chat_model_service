# 开发教学与测试计划

## 1. 从零理解 S6

先运行一次通过评测，再创建一个缺少引用/拒答约束的 draft，使用第一次 run 作为 baseline。观察第二次运行的 `failed_cases` 和 `quality_score_vs_baseline`；历史 run 不修改，修复后创建新 run。

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_quality_reliability.py -q
```

关键代码：`qa_api/quality.py` 负责数据集、快照、指标和门禁；`quality_api.py` 只处理权限与契约；`observability.py` 负责 OTel 与进程窗口。新增指标前先问：值是否有界、是否含个人/租户信息、是否会无限增长标签数量。

## 2. 本地全栈

```powershell
docker compose --env-file .env -f infra\compose\compose.yaml up -d --build
.\.venv\Scripts\python.exe scripts\smoke_s6.py
docker compose --env-file .env -f infra\compose\compose.yaml exec -T prometheus promtool check rules /etc/prometheus/alerts.yaml
```

打开 Grafana，确认五个面板有数据；Prometheus Targets 中 `enterprise-qa-api` 为 up；指标系列的 `http_route` 必须是模板而不是真实 UUID。

## 3. 韧性工具

```powershell
.\.venv\Scripts\python.exe scripts\fault_s6.py
.\.venv\Scripts\python.exe scripts\drill_s6_recovery.py
.\.venv\Scripts\python.exe scripts\load_s6.py --profile smoke --duration 3 --rps 2
```

不要在共享或生产环境直接使用 `--allow-nonlocal`。真实压测必须先确认 URL、租户、数据清理、费用、告警和值班人员。

## 4. 测试矩阵

- 单元/集成：门禁通过/失败、baseline delta、权限、租户安全、未知数据集/候选、外部 Worker fail-closed、W3C trace、快照边界。
- 契约：Runtime 与 canonical S6 路径和请求字段一致；YAML/ref 校验。
- 数据库：Base metadata、0007 up/down/up、PostgreSQL head。
- 静态：Ruff、mypy strict、ESLint、TypeScript、Next production build。
- 全栈：OIDC、评测、审计、usage、operations、Prometheus、Grafana。
- 韧性：429、timeout、missing usage、post-fault health、隔离恢复不变量。

## 5. Definition of Done

任何新指标、接口或恢复步骤都必须同步更新 OpenAPI/DDL、测试、ADR/决策、风险、Runbook 和 Gate；只有目标环境证据才能关闭生产阻断项。
