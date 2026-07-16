# 发布架构与不可变制品证据

## 组件边界

`ReleaseService` 是本地决策状态机；数据库保存候选/UAT/签署/事件；`PolicyEngine` 执行权限；`GovernanceService` 写租户审计链。目标环境的 GitHub Actions、registry、Argo Rollouts/Flagger、Prometheus/APM 和 Pager 属于外部可信边界。

## 候选清单

| 字段 | 来源 | 约束 |
|---|---|---|
| `release_version` | Release Manager | tenant 内唯一，不可变 |
| `git_sha` | CI | 40 位小写 SHA |
| `image_digest` | registry | `sha256:` + 64 hex |
| `sbom_digest` | SBOM/attestation | `sha256:` + 64 hex |
| `db_migration` | Alembic | 本阶段为 `20260716_0008` |
| `prompt_versions` | 评测快照 | 服务端派生 |
| `retrieval_versions` | 评测配置 checksum | 服务端派生 |
| `model_route_versions` | 批准路由清单 | 至少一项 |
| `dataset_version/eval_run_id` | 质量平台 | 必须通过 |
| `rollback_target` | 已批准基线 | 不得等于候选 |
| `known_issues` | Release Manager | 只存安全摘要 |

清单按 UTF-8、key 排序、紧凑 JSON 规范化后计算 SHA-256。清单 digest 证明数据库内字段未被静默替换；镜像真实性仍依赖 registry 签名与 provenance。

## 状态

`draft → qualified → approved → rolling_out → completed`。失败分支为 `rejected`、`stopped`、`rolled_back`；这些终止态不得恢复为同一候选，修复必须创建新版本。
