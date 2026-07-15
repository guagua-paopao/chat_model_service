# S1 工程骨架、认证与租户证据包

> 版本：s1-v1.0  
> 日期：2026-07-15  
> 结论：**条件通过，可进入 S2 合成开发；真实数据、企业 IdP 与生产部署仍禁止**

S1 已交付一条可运行的企业级最小纵切：浏览器通过本地 OIDC Authorization Code + PKCE 登录，Next.js BFF 使用 HttpOnly 会话调用 FastAPI，API 从已验证 token 建立可信租户上下文，用户可以读取 `/me` 并创建、查询、修改、删除自己的会话。PostgreSQL 迁移、Worker、Redis、MinIO、OpenTelemetry Collector、CI、Docker Compose 与 Helm 骨架同时建立。

## 文档导航

| 文档 | 用途 |
|---|---|
| [S1 需求与范围](01-s1-requirements-and-scope.md) | 场景、需求、验收标准、范围边界 |
| [架构与安全设计](02-architecture-and-security-design.md) | 组件、信任边界、认证/授权、部署设计 |
| [API 与数据设计](03-api-and-data-design.md) | S1 接口、字段、错误、表结构、并发语义 |
| [本地开发教学](04-local-development-tutorial.md) | 从零安装、启动、登录、调试和三项教学实验 |
| [测试与验证报告](05-test-and-verification-report.md) | 自动化结果、Compose 冒烟、供应链证据与限制 |
| [风险与开放项](06-risks-and-open-items.md) | 生产阻断项、Owner、退出条件 |
| [S1 Gate 评审](07-s1-gate-review.md) | 逐条退出条件和阶段结论 |
| [决策日志](decision-log.md) | S1 重要决策、理由、复审触发器 |
| [机器清单](manifest.yaml) | 阶段版本、产物、门禁、下一阶段授权范围 |

## 可执行产物

- API：`apps/api`；Fake IdP：`apps/fake-idp`；Worker：`apps/worker`；Web：`apps/web`。
- 数据库迁移：`apps/api/migrations/versions/20260715_0001_s1_identity_conversation.py`。
- 契约：`docs/enterprise-qa-system/openapi.yaml`，S1 已实现其中身份、会话和健康检查接口。
- 本地环境：`infra/compose/compose.yaml`；生产骨架：`infra/helm/qa-system`。
- 自动化：`scripts/setup.ps1`、`scripts/check.ps1`、`scripts/dev.ps1`、`scripts/smoke_s1.py`、`.github/workflows/`。
- 测试：`tests/unit`、`tests/integration`。

## 使用本证据包

1. 新开发者先按 [本地开发教学](04-local-development-tutorial.md) 完成启动和冒烟。
2. 修改公开接口时先改 canonical OpenAPI 与契约测试，再改实现。
3. 改变认证、租户、浏览器会话、并发或供应链边界时先新增或 supersede ADR。
4. 开始 S2 前阅读 [Gate 评审](07-s1-gate-review.md) 中仍然生效的条件；S2 只能使用合成数据与 Fake Provider。

