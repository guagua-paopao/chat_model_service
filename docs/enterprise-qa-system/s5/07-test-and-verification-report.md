# S5 测试与验证报告

> 日期：2026-07-16  
> 范围：本地/Compose 合成与明确批准的非敏感数据  
> 结论：S5 工程候选门禁通过；真实企业集成、staging 和生产门禁未通过。

## 1. 可复验结论

| 证据域 | 命令或范围 | 结果 |
|---|---|---|
| Python 功能回归 | `pytest -W error` | 66 passed，35 subtests passed |
| Python 覆盖率 | `qa_api` + `fake_idp` | 88.64%，门槛 85% |
| S5 核心覆盖率 | `governance.py` / `governance_api.py` | 86% / 96% |
| 静态检查 | Ruff / Mypy strict | passed / passed |
| 契约 | 9 份 YAML、OpenAPI `$ref`、S0～S5 必需路径 | 222 refs、35 paths，passed |
| S4 质量回归 | 20-case 合成黄金集 | 7 项指标通过；越权泄漏 0 |
| SQLite migration | empty → head → base → head | passed，最终 `20260716_0006` |
| PostgreSQL migration | Compose PostgreSQL 16 | `20260716_0006 (head)` |
| Web | ESLint / TypeScript / production build | passed；`/admin` 生成成功 |
| Compose | config + 8 services | passed；API、PostgreSQL、Redis、MinIO、Fake IdP healthy |
| S5 smoke | 身份、组、配置门禁、回滚、配额、审计 | passed；published v8、rollback v9、20 audit events |
| S4 smoke | 上传、摄取、检索、回答、引用、反馈 | passed |
| Python 依赖审计 | `pip-audit -r requirements.lock --no-deps` | 0 known vulnerabilities |
| Web 生产依赖审计 | `npm audit --omit=dev --audit-level=high` | 0 vulnerabilities |

以上数字是本次工作区的时点证据，不是未来持续合规承诺。`pip-audit` 提示锁文件尚未包含哈希；漏洞库没有命中也不等于供应链可信。

## 2. S5 关键验收覆盖

### 2.1 身份、策略与 ACL

- 普通员工访问管理 API 得到 403；权限未知时集中 `PolicyEngine` fail closed。
- JWT 只提供身份线索；role/group 从当前 tenant 目录表解析。
- disabled 用户在下一请求得到 `USER_DISABLED`；生命周期更新要求 ETag、原因和审批号。
- group-only 文档 ACL 在候选检索前生效，引用仍按当前目录态重新鉴权。
- 本地 persona 保持职责最小化，普通 demo employee 未被提升为治理管理员。

### 2.2 配置治理

- Draft 使用 exact schema、边界校验和 canonical checksum；历史版本不可修改。
- 客户端不能提交 `gate_result`；dataset/evaluator/version/evidence 均由服务器生成。
- 未评测或评测失败不能审批；创建者即使临时获得审批角色仍因职责分离得到 409。
- 发布要求 passing evidence 和独立批准；rollback 创建更高版本克隆，不覆盖历史行。
- 故意把 `min_relevance` 降至 0.1 时，本地结构/安全门禁失败，审批继续被阻断。

该 evaluator 仅验证结构、安全下界与已知配置不变量。它不验证真实业务准确率、中文质量、claim-level groundedness、红队或 Provider 差异；staging/production 配置会拒绝启用它。

### 2.3 配额、审计和事件

- Chat 准入在 tenant 数据库锁下更新分钟窗口和 TTL lease，并查询日 token/月成本账本；失败不调用模型，`finally` 释放 lease。
- 配额策略更新要求 ETag、原因、审批号并写治理事件。
- 高风险事件使用 tenant sequence + previous hash + event hash；测试直接修改数据库 reason 后，完整性检查定位到首个错误 sequence。
- 事件状态机拒绝非法跳转，解决/关闭要求安全处置摘要；摘要 API 强制 tenant 范围和最多 31 天。

数据库哈希链只能发现修改，不能阻止拥有数据库重写能力的攻击者重算整条链。生产必须外送并锚定到独立 SIEM/WORM。

## 3. 回归质量指标

| 指标 | 结果 | 工程门槛 |
|---|---:|---:|
| Recall@10 | 1.000 | ≥ 0.90 |
| Citation precision | 1.000 | ≥ 0.90 |
| Citation completeness | 1.000 | ≥ 0.90 |
| Groundedness proxy | 1.000 | ≥ 0.90 |
| Abstention precision | 1.000 | ≥ 0.90 |
| Abstention recall | 1.000 | ≥ 0.90 |
| Unauthorized leakage | 0 | 0 |

这是 Fake Embedding/Reranker/Model 与小型英文合成数据的确定性回归，只证明 S5 没有破坏 S4 基线。

## 4. 迁移与部署证据

- Alembic `0005` 新增目录组、配置评测/审批、配额窗口/租约、治理审计和安全事件；`0006` 增加活动 token 预留和单 published 数据库约束。SQLite 全链可升降再升级。
- Compose 中 PostgreSQL 16 报告 head 为 `20260716_0006`，事务 DDL 生效。
- 8 个服务在同一 Compose 项目运行；S5 和 S4 smoke 均通过真实 HTTP、Fake OIDC、PostgreSQL、Redis 和 MinIO 边界。
- API、Worker、Web 容器镜像已构建；Next production build 明确列出 `/admin` 路由。
- Helm CLI、Kubernetes 集群、Ingress、NetworkPolicy、PDB/HPA 和 secret manager 未验证。

## 5. 未完成或不应误读为通过

- 无企业 OIDC/SCIM、真实组同步、离职传播 P95/P99 或乱序/重放演练。
- 无外部独立评测 Worker、业务黄金集、holdout、红队和具名审批签字。
- 无 WORM/SIEM 外送与对账；无真实告警触发、on-call 演练或证据保全平台。
- 无跨实例取消；数据库配额尚未做目标并发/锁竞争/failover 压测，上传容量和服务账号配额未实现。
- 无真实数据 UAT、Provider 审批、Kubernetes、性能、备份恢复、RPO/RTO 或灾难演练。
- 本机未安装 Helm 和 gitleaks；秘密扫描、SBOM、镜像签名、许可策略须由 CI/制品平台补证。

## 6. 复验命令

```powershell
.\.venv\Scripts\python.exe -m ruff check apps/api/src apps/api/scripts apps/fake-idp/src scripts tests
.\.venv\Scripts\python.exe -m mypy --strict apps/api/src
.\.venv\Scripts\python.exe -m pytest -W error --cov=qa_api --cov=fake_idp --cov-fail-under=85
.\.venv\Scripts\python.exe scripts/evaluate_s4.py
.\.venv\Scripts\python.exe scripts/validate_contracts.py
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run typecheck
```

完整迁移、构建、在线审计与 Compose smoke 的环境变量和步骤见 [开发教学与测试计划](06-development-tutorial-and-test-plan.md)。
