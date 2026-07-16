# S7 测试与验证报告

日期：2026-07-16。数据范围：合成、公开或明确批准的非敏感数据。

## 结论

S7 本地发布控制面和合成发布演练通过；真实数据、staging 和 production 仍为 NO-GO。本报告证明实现、迁移、状态机与本地集成链路可运行，不构成生产验收、CAB 批准或真实业务 UAT 签收。

## 自动化与静态门禁

| 检查 | 结果 |
| --- | --- |
| Pytest 全量回归 | 76 tests + 35 subtests，通过 |
| Python 覆盖率 | 89.18%，高于 85% 门禁 |
| S7 正/负路径 | 完整灰度、普通退化自动停止、人工回滚、安全泄露自动回滚、职责隔离、UAT 不可变、正式环境 fail-closed，通过 |
| Ruff / compileall | 通过 |
| mypy strict | `apps/api/src` 25 个生产源码文件通过 |
| OpenAPI / YAML | 9 个 YAML、47 条 canonical paths、285 个引用，通过 |
| Web | ESLint、TypeScript typecheck、Next.js 16.2.10 production build，通过 |
| Python 依赖审计 | `pip-audit`：0 个已知漏洞 |
| Web 生产依赖审计 | `npm audit --omit=dev`：0 个已知漏洞 |

仓库既定 CI 只对 `apps/api/src` 执行 strict mypy。一次额外的全脚本/测试诊断扫描发现 351 个历史类型问题，主要是 `unittest` 动态类属性和 JSON `Any`；它不影响既定门禁结论，但应在后续单独建立测试代码类型化改进计划，不能表述为“全仓 mypy 通过”。

## 数据库、质量与恢复验证

- SQLite 隔离库完成 `base → 0008 → 0007 → 0008` 往返迁移。
- Compose PostgreSQL 16/pgvector 完成 `0007 → 0008`，迁移容器退出码为 0，`alembic_version=20260716_0008`。
- S4 20 条合成评测门禁通过：Recall@10、引用精度/完整性、groundedness、拒答精度/召回均为 1.0，越权泄露为 0。
- S6 五类 Fake Provider 故障场景和四项本地恢复不变量继续通过；这些仍不是生产 Provider、PITR 或跨区域 DR 证据。

## 全栈验收

- Compose 配置解析通过；10 个长期服务启动，API、Fake IdP、PostgreSQL、Redis、MinIO 健康，迁移 Job 正常退出。
- S7 smoke 在真实本地 PostgreSQL/Redis/MinIO/Fake IdP 链路创建评测与不可变候选，写入 UC-01～UC-05、五类签署，执行 `dark → 5% → 25% → 50% → 100%`，最终 `completed`，事件数为 5。
- S3、S4、S5、S6 全栈 smoke 全部回归通过。
- 本机没有 Helm CLI，因此仅验证了 Helm 模板参数和正式环境 fail-closed 配置，未执行 `helm lint/template/install`；该项继续作为 staging 阻断项。

## 解释限制

候选中的镜像/SBOM digest 是合成格式数据，不证明 registry 中存在、已扫描或已签名；UAT/签署来自开发 persona；灰度观察为合成数值；本地 API 不操作 Kubernetes 流量。真实发布还必须接入企业 IAM/CAB、registry attestation、可信观测、外部 Rollout Controller、生产同构 staging、目标压测、真实 UAT 和具名运维签收。
