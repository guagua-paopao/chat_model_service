# S1 API 与数据设计

## 1. 契约规则

- API 前缀：`/api/v1`；JSON 使用 snake_case；时间为带时区 RFC 3339；ID 为 UUID。
- 输入模型 `extra=forbid`，未知字段返回 422，避免客户端拼写错误被静默忽略。
- 错误媒体类型为 `application/problem+json`；每个响应带可用于排障的 `request_id`。
- canonical 契约是 `../openapi.yaml`。其中包含未来阶段接口；本文件只描述 S1 已实现端点。
- 浏览器调用同源 `/api/qa/*` BFF，BFF 再映射到 API；服务到服务调用可直接使用 bearer token。

## 2. 公共请求/响应头

| Header | 方向 | 必填 | 说明 |
|---|---|---:|---|
| `Authorization: Bearer <token>` | 请求 | 除健康检查外是 | token 必须经过签名和声明验证 |
| `X-Request-ID` | 请求/响应 | 请求否 | 合法值可透传；否则服务生成，响应总是返回 |
| `X-Trace-ID` | 响应 | 否 | 当前链路追踪标识；生产由 OTel/W3C trace context 完善 |
| `Content-Type: application/json` | 请求 | 有 body 时 | 最大请求体默认 1 MiB |
| `ETag: "vN"` | 响应 | 单资源是 | 资源乐观版本，不是内容 hash |
| `If-Match: "vN"` | PATCH 请求 | 是 | 防止丢失更新 |
| `X-CSRF-Token` | BFF 变更请求 | 是 | 必须与 `qa_csrf` cookie 一致；直连 API 不使用此机制 |

## 3. 已实现接口

| 方法与路径 | 权限 | 请求 | 成功响应 |
|---|---|---|---|
| `GET /api/v1/health/live` | 无 | 无 | 200 `HealthResponse` |
| `GET /api/v1/health/ready` | 无 | 无 | 200 `ReadinessResponse`；DB 失败为 503 |
| `GET /api/v1/me` | 已认证 | 无 | 200 `MeResponse` |
| `POST /api/v1/conversations` | `qa:conversation:write` | `ConversationCreate` | 201 + ETag + Location |
| `GET /api/v1/conversations` | `qa:conversation:read` | `limit/cursor/status` | 200 `ConversationListResponse` |
| `GET /api/v1/conversations/{id}` | `qa:conversation:read` | UUID | 200 + ETag；不可见 404 |
| `PATCH /api/v1/conversations/{id}` | `qa:conversation:write` | `If-Match` + `ConversationPatch` | 200 + 新 ETag |
| `DELETE /api/v1/conversations/{id}` | `qa:conversation:write` | UUID | 204，执行软删除 |

### 3.1 HealthResponse / ReadinessResponse

| 字段 | 类型 | 规则 |
|---|---|---|
| `status` | string | live 固定 `ok`；ready 固定 `ready` |
| `checks` | object | readiness 当前返回 `{ "database": "ok" }` |

### 3.2 MeResponse

| 字段 | 类型 | 来源 |
|---|---|---|
| `id` | UUID | 数据库用户 ID，不返回 OIDC subject |
| `tenant.id` | UUID | 已签名 token 定位后由数据库确认 |
| `tenant.code` | string | 租户稳定业务代码 |
| `roles[]` | string[] | 当前有效 `user_roles` 映射，排序返回 |
| `permissions[]` | string[] | 角色 permission 合并去重，排序返回 |
| `display_name` | string | 用户资料；日志禁止记录 |
| `locale` | string | 如 `zh-CN` |

### 3.3 ConversationCreate

| 字段 | 类型 | 必填 | 约束/默认 |
|---|---|---:|---|
| `title` | string | 否 | 默认“新对话”，trim 后 1–300 字符 |
| `knowledge_base_ids` | UUID[] | 否 | 默认空；最多 10 个且不可重复；S1 只保存不验证知识库存在性 |
| `channel` | enum | 是 | `web` / `api` / `approved_connector` |
| `metadata` | object | 否 | 默认空，最多 20 个一级属性；不得放密钥/正文/敏感身份信息 |

服务端生成 `id`、`tenant_id`、`user_id`、`status=active`、`version=1` 与时间；客户端不能提交前三个作用域字段。

### 3.4 ConversationResponse

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUIDv7 | 时间有序资源 ID |
| `title` | string | 会话标题 |
| `status` | enum | 外部只返回 `active` / `archived`；deleted 不可查询 |
| `channel` | enum | 创建来源 |
| `knowledge_base_ids` | UUID[] | 默认知识库选择，S3 才生效 |
| `metadata` | object | 非安全关键扩展信息 |
| `created_at` / `updated_at` | datetime | UTC、带时区 |

### 3.5 列表、PATCH 与 DELETE

- 列表参数：`limit` 默认 20、范围 1–100；`status` 为 `active|archived`；`cursor` 最大 1024 字符。
- 列表顺序固定 `(created_at DESC, id DESC)`。`next_cursor` 为 HMAC 签名、不透明、绑定 tenant/user/status 的 keyset 游标；客户端不得解析或修改。
- PATCH body 至少含一个字段：`title`（1–300，非空白）或 `status`（`active|archived`）。
- PATCH 必须提交最近一次 GET/POST 的 ETag。缺失 428，格式错误 400，已过期 412。
- DELETE 将 `status` 置为 deleted 并写 `deleted_at`；重复删除或不可见资源返回相同 404。

## 4. Problem+JSON

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | URI string | 稳定问题类型 URI |
| `title` | string | 简短安全标题 |
| `status` | integer | HTTP 状态码 |
| `code` | string | 稳定机器码，如 `TOKEN_INVALID`、`ETAG_MISMATCH` |
| `detail` | string | 不泄露资源存在性/内部异常的安全描述 |
| `instance` | string? | 请求路径 |
| `request_id` | string | 支持工单关联 |
| `retryable` | boolean | 客户端是否可自动重试 |
| `errors[]` | object[]? | 校验错误的 `field/code/message` |

主要状态：401 缺失/无效身份；403 禁用/权限不足；404 不存在或不可见；412 ETag 冲突；422 字段校验；428 缺少 If-Match；503 readiness 失败。

## 5. 数据字典

所有租户业务表都含 `tenant_id`；迁移是唯一生产 schema 入口。

### `tenants`

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `id` | UUID PK | 租户内部 ID |
| `code` | varchar(64) unique | 稳定租户代码 |
| `name` | varchar(200) | 展示名 |
| `status` | varchar(24) | `active` 等状态 |
| `default_locale` | varchar(16) | 默认语言 |
| `timezone` | varchar(64) | IANA 时区 |
| `settings` | JSON | 非密钥配置 |
| `data_classification` | varchar(24) | 默认数据等级 |
| `created_at/updated_at` | timestamptz | 审计时间 |

### `users`

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `id` | UUID PK | 用户内部 ID |
| `tenant_id` | UUID FK | 租户边界 |
| `auth_issuer` | varchar(512) | OIDC issuer |
| `auth_subject` | varchar(255) | issuer 内稳定 subject |
| `email` | varchar(320) nullable | 资料，不作为主身份键且不进普通日志 |
| `display_name` | varchar(200) | 展示名 |
| `status` | varchar(24) | `active/disabled` |
| `locale` | varchar(16) | 用户语言 |
| `last_login_at` | timestamptz nullable | 登录时间（后续完善写入） |
| `created_at/updated_at` | timestamptz | 审计时间 |

唯一约束 `(tenant_id, auth_issuer, auth_subject)`；另有 `(tenant_id,id)` 供组合外键引用。

### `roles` / `user_roles`

`roles`：`id`、`tenant_id`、`code`、`name`、`permissions` JSON 数组、`is_system`、时间；唯一 `(tenant_id,code)` 和 `(tenant_id,id)`。

`user_roles`：复合主键 `tenant_id,user_id,role_id`，`valid_from`、`valid_until`、`created_at`；组合外键确保用户和角色属于同一租户。

### `conversations`

`id` UUID PK；`tenant_id,user_id` 组合关联用户；`title` varchar(300)；`status` varchar(16)；`channel` varchar(32)；`default_kb_ids` JSON；`metadata` JSON；`version` integer；`created_at/updated_at/deleted_at`。索引覆盖 `tenant_id,user_id,updated_at,id`，列表查询另以 created_at/id 做稳定排序。

### `messages`

S2 预留表：`id`、`tenant_id`、`conversation_id`、`role`、`content`、`status`、`sequence_no`、`created_at`；组合外键绑定同租户会话，唯一 `(tenant_id,conversation_id,sequence_no)`。S1 API 尚未读写消息。

### `audit_logs`

`id`、`tenant_id`、`actor_user_id`、`action`、`resource_type`、`resource_id`、`result`、`request_id`、`trace_id`、`details_safe`、`occurred_at`。`details_safe` 只放筛选后的字段，不得放 token、email、问题正文或文档正文。

## 6. 迁移与种子数据

版本 `20260715_0001` 创建上述表、约束和索引；支持 downgrade 到 base。Compose 先运行独立 migrate 容器，成功后才启动 API。API 在 Compose 中禁止自动建表；本地 SQLite 测试可显式启用。

合成种子包含 `demo_corp`、`other_corp` 两个租户，active/disabled/other 三类用户和 employee 角色，用于负向隔离测试。初始化显式按 tenant → user/role → user_role 分批 flush，保证 PostgreSQL 外键插入顺序。

