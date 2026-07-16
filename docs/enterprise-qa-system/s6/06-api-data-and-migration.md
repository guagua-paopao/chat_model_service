# API、字段、数据与迁移

## 1. 新增接口

| 方法与路径 | 权限 | 说明 |
|---|---|---|
| `POST /api/v1/evaluations/runs` | `qa:evaluation:run` | 运行 1–5 个候选，201 返回完成记录 |
| `GET /api/v1/evaluations/runs` | `qa:evaluation:read` | 最多 100 条，可按 gate 过滤 |
| `GET /api/v1/evaluations/runs/{id}` | `qa:evaluation:read` | 租户隔离的单次读取 |
| `GET /api/v1/usage` | `qa:usage:read` | 最长 31 天，按 none/model/operation 分组 |
| `GET /api/v1/admin/operations/snapshot` | `qa:operations:read` | 进程+租户诊断摘要 |

完整请求/响应以 `openapi.yaml` 1.6.0-s6 为准。所有接口的 tenant 来自认证上下文，不接受请求字段。

## 2. `evaluation_runs` 字段字典

| 字段 | 类型 | 约束/语义 |
|---|---|---|
| id / tenant_id | UUID | 主键；tenant 复合唯一 |
| dataset_version_id/checksum | varchar(128)/char(64) | 不可变数据集身份 |
| candidate_config_ids | JSON array | 1–5 个 UUID 字符串 |
| candidate_config_snapshots | JSON | prompt/config/checksum 的执行时快照；不对普通 API 返回 |
| baseline_run_id | UUID nullable | 同租户完成运行 |
| status | completed/failed | 本地同步运行终态 |
| metrics/thresholds/deltas | JSON | 指标、服务器阈值、基线差异 |
| gate_result | passed/failed | 发布判定 |
| failed_cases | JSON array | 仅 candidate ID、case ID、control、check code |
| amount/currency | numeric(18,8)/char(3) | 评测成本；本地为 0 USD |
| code_revision/evaluator_version | varchar | 可复现身份 |
| tags/error_code | JSON/varchar | 低风险检索标签、错误码 |
| created_by/timestamps | UUID/timestamptz | Actor 与执行时间 |

索引：`(tenant_id, created_at)`、`(tenant_id, gate_result, created_at)`。禁止跨租户 baseline；生产外部 Worker 需增加幂等/队列状态时必须新建迁移和 ADR。

## 3. 迁移

Revision `20260716_0007` 只新增表和索引，可回退到 `20260716_0006`。验证顺序为 `upgrade head → downgrade 0006 → upgrade head`，SQLite 已通过；PostgreSQL Compose 已升级到 0007。

生产步骤：备份/PITR 点 → 只运行 migration Job → 核验 revision/索引/约束 → 启动 API → smoke。禁止应用进程自动建表，失败时停止部署并按变更单决定 downgrade。
