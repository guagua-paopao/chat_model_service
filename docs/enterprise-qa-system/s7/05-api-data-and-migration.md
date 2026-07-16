# API、数据与迁移

## API

| 方法与路径 | 权限 | 语义 |
|---|---|---|
| `POST /admin/releases` | `qa:release:create` | 冻结候选 |
| `GET /admin/releases`、`/{id}` | `qa:release:read` | 读取完整证据 |
| `POST /{id}/uat-results` | `qa:release:uat` | 追加 UAT |
| `POST /{id}/signoffs` | `qa:release:signoff` | 类别绑定签署 |
| `POST /{id}/rollout/start` | `qa:release:rollout` | 从 dark 开始 |
| `POST /{id}/rollout/advance` | `qa:release:rollout` | 门禁后前进/停止/回滚 |
| `POST /{id}/rollout/stop` | `qa:release:rollout` | 人工停止 |
| `POST /{id}/rollout/rollback` | `qa:release:rollout` | 回滚至冻结目标 |

错误码包括 `RELEASE_EVALUATION_GATE_FAILED`、`RELEASE_UAT_CLOSED`、`UAT_RESULT_IMMUTABLE`、`RELEASE_ROLE_REQUIRED`、`RELEASE_SIGNOFF_IMMUTABLE`、`RELEASE_NOT_APPROVED`、`ROLLOUT_STAGE_SEQUENCE_INVALID` 和 `EXTERNAL_RELEASE_CONTROLLER_REQUIRED`。

## 数据与迁移

迁移 `20260716_0008` 新增 `release_candidates`、`release_uat_results`、`release_signoffs`、`release_rollout_events`。tenant+release/version/case/category/actor/sequence 唯一约束阻断重复与覆盖。

上线必须 expand/contract：先迁移新增表，再部署兼容应用；回滚应用不删除 S7 表。若迁移后已有 S7 数据，数据库 downgrade 只允许隔离演练，生产使用前向修复。
