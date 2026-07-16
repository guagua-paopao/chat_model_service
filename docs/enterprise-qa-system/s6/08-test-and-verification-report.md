# S6 测试与验证报告

日期：2026-07-16。数据范围：合成、公开或明确批准的非敏感数据。

## 已验证

- S6 质量/可靠性集成与契约专项测试通过。
- 全量 Python：72 tests + 35 subtests，88.84% coverage（门槛 85%）。
- Ruff、mypy strict、ESLint、TypeScript typecheck、Next production build 通过。
- Python 锁定依赖与 npm production dependencies 在线审计：已知漏洞均为 0。
- OpenAPI/YAML/ref 校验通过：9 个 YAML、247 个引用、39 条 canonical paths。
- Alembic 0007 SQLite `up/down/up` 通过；PostgreSQL Compose migration 成功。
- Docker Compose 配置校验通过；当前主机未安装 Helm，Helm lint/目标集群安装未执行，继续作为生产阻断项。
- Compose 长期服务：API、Worker、Web、PostgreSQL、Redis、MinIO、Fake OIDC、OTel Collector、Prometheus、Grafana 共 10 个运行，API 健康。
- Prometheus targets：`enterprise-qa-api` 与 `prometheus` 均 up；8 个 S6 metric series family 可见。
- `promtool check rules`：4 条规则成功。
- S6 full-stack smoke：评测、读回、usage、operations、Prometheus、Grafana 通过。
- 短时负载：2 RPS × 3 秒，6/6 成功，P95 74.88 ms。
- 故障注入：5/5 场景通过。
- 恢复演练：4/4 不变量通过；合成 RPO 0.013 s、RTO 0.118 s。
- S4 20-case 评测门禁继续通过；S4/S5/S6 全栈 smoke 均通过。

## 解释限制

上述性能来自本机小样本；恢复来自 SQLite/本地目录；质量来自 24 条结构性合成用例；Provider、OIDC、对象存储均为本地替身。它们证明工程路径可执行，不证明生产性能、业务质量、跨区域恢复或真实供应商韧性。

## 最终归档结论

代码、契约、迁移、前端构建、依赖审计、跨阶段回归、负载/故障/恢复工具和本地观测栈均已形成可重复证据。该结论仅支持 `local_engineering_pass`；生产阻断项与签字状态以 [S6 Gate](09-s6-gate-review.md) 为准，不通过文档豁免。
