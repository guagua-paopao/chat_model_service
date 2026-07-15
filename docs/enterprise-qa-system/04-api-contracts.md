# 04. API 与事件契约

## 1. 通用规范

- Base URL：`https://qa.example.com/api/v1`；版本放路径，资源名使用复数名词。
- 编码：UTF-8 JSON；时间为 RFC 3339 UTC；ID 为 UUID 字符串；金额为十进制定点字符串。
- 认证：Web 使用 OIDC 会话/BFF，系统集成使用 OAuth2 Client Credentials；作用域如 `qa:ask`、`kb:write`。
- 租户：由 token/服务端映射解析。`X-Tenant-Id` 只允许系统管理员或明确授权服务账号切换，普通调用者传入即忽略或拒绝。
- 关联：客户端可传 `X-Request-ID`（UUID/受限字符）；服务端总是回传并生成 `traceparent`。
- 幂等：创建文档、完成上传、启动重建等接口接受 `Idempotency-Key`；键在租户+调用方+操作范围唯一。
- 并发控制：可变资源返回 `ETag`；更新时使用 `If-Match`，冲突返回 412。
- 分页：游标分页 `?limit=20&cursor=...`，响应 `next_cursor`；不向外暴露数据库 offset。
- API 返回字段使用 `snake_case`，枚举值小写；未知响应字段客户端应忽略。
- 限流响应包含 `Retry-After`；不得把供应商原始错误、内部堆栈或密钥透传给客户端。

## 2. 端点总表

### 2.1 会话与问答

| Method | Path | Scope | 说明 |
|---|---|---|---|
| POST | `/conversations` | `qa:ask` | 新建会话 |
| GET | `/conversations` | `qa:ask` | 本人会话列表 |
| GET | `/conversations/{id}` | `qa:ask` | 会话及分页消息 |
| PATCH | `/conversations/{id}` | `qa:ask` | 改标题/归档 |
| DELETE | `/conversations/{id}` | `qa:ask` | 逻辑删除本人会话 |
| POST | `/chat/completions` | `qa:ask` | 问答；`stream=true` 返回 SSE |
| POST | `/messages/{id}/cancel` | `qa:ask` | 取消进行中的回答 |
| POST | `/messages/{id}/retry` | `qa:ask` | 从指定消息创建回答分支 |
| GET | `/messages/{id}/citations/{citation_id}` | `qa:ask` | 再鉴权后读取引用详情/短期原文 URL |
| POST | `/messages/{id}/feedback` | `qa:feedback` | 提交或更新本人的反馈 |

### 2.2 知识库与文档

| Method | Path | Scope | 说明 |
|---|---|---|---|
| POST/GET | `/knowledge-bases` | `kb:write/kb:read` | 创建/列表 |
| GET/PATCH/DELETE | `/knowledge-bases/{id}` | `kb:read/kb:write` | 详情/修改/归档 |
| POST | `/knowledge-bases/{id}/documents` | `document:write` | 创建文档版本并获取上传信息 |
| POST | `/documents/{id}/upload-complete` | `document:write` | 校验上传并启动摄取 |
| GET | `/documents/{id}` | `document:read` | 文档/版本/状态 |
| PATCH | `/documents/{id}` | `document:write` | 标题、元数据、ACL 等 |
| POST | `/documents/{id}/publish` | `document:publish` | 原子发布已就绪版本 |
| POST | `/documents/{id}/reindex` | `document:write` | 使用新配置重建 |
| DELETE | `/documents/{id}` | `document:write` | 下线并进入删除流程 |
| GET | `/jobs/{id}` | `document:read` | 摄取/评测任务状态 |
| POST | `/jobs/{id}/retry` | `document:write` | 重试允许的失败任务 |
| POST | `/retrieval/search` | `qa:search` | 授权范围内的调试检索 |

### 2.3 管理与运营

| Method | Path | Scope | 说明 |
|---|---|---|---|
| GET | `/models` | `model:read` | 可用模型和能力，不返回 secret |
| POST | `/model-routes/{id}/test` | `model:manage` | 对批准样例做连通测试 |
| GET/POST | `/prompts` | `prompt:read/manage` | 列表/新草稿 |
| POST | `/prompts/{id}/versions/{version}/publish` | `prompt:publish` | 审批后发布 |
| POST | `/evaluations/runs` | `evaluation:run` | 启动离线评测 |
| GET | `/evaluations/runs/{id}` | `evaluation:read` | 指标和失败样本 |
| GET | `/usage` | `usage:read` | 按时间/租户/模型汇总 |
| GET | `/audit-logs` | `audit:read` | 审计游标查询 |
| POST | `/audit-exports` | `audit:export` | 异步导出 |
| GET | `/health/live` | public/internal | 进程存活，不检查外部依赖 |
| GET | `/health/ready` | internal | 流量准入所需依赖检查 |

## 3. 创建会话

`POST /api/v1/conversations`

请求：

```json
{
  "title": "差旅制度咨询",
  "knowledge_base_ids": ["0190f6dd-49ab-7a17-9a10-84f3e23f65cc"],
  "channel": "web",
  "metadata": {"business_scene": "employee_policy"}
}
```

| 字段 | 类型 | 必填 | 校验 |
|---|---|---:|---|
| `title` | string |  | 1–300；空缺时异步生成 |
| `knowledge_base_ids` | uuid[] |  | 最大 10；逐个鉴权 |
| `channel` | enum | ✓ | `web/api/approved_connector` |
| `metadata` | object |  | ≤ 8 KB；仅接受场景配置白名单字段 |

响应 `201`：

```json
{
  "id": "0190f700-42d2-75de-90b8-5b06a4bb043e",
  "title": "差旅制度咨询",
  "status": "active",
  "knowledge_base_ids": ["0190f6dd-49ab-7a17-9a10-84f3e23f65cc"],
  "created_at": "2026-07-15T02:15:10Z"
}
```

## 4. 流式问答

`POST /api/v1/chat/completions`，`Accept: text/event-stream`

请求：

```json
{
  "conversation_id": "0190f700-42d2-75de-90b8-5b06a4bb043e",
  "message": "出差住宿费的报销上限是多少？",
  "knowledge_base_ids": ["0190f6dd-49ab-7a17-9a10-84f3e23f65cc"],
  "stream": true,
  "model_policy": "balanced",
  "response_mode": "grounded_answer",
  "client_context": {"locale": "zh-CN"}
}
```

| 字段 | 类型 | 必填 | 规则 |
|---|---|---:|---|
| `conversation_id` | uuid | ✓ | 必须属于当前用户或获授权服务主体 |
| `message` | string | ✓ | 1–8000 字符；控制 token 后再调用模型 |
| `knowledge_base_ids` | uuid[] |  | 最大 10；为空使用会话默认值，服务端重新鉴权 |
| `stream` | boolean | ✓ | 首版推荐 `true`；`false` 返回完整 JSON |
| `model_policy` | enum |  | `fast/balanced/quality`；映射到服务端发布路由 |
| `response_mode` | enum |  | `grounded_answer/search_only`；首版不允许 arbitrary agent |
| `client_context.locale` | string |  | BCP 47；不接受客户端传角色/租户 |

请求成功后立即返回 `200 text/event-stream`。SSE 事件使用 `event:` + 单行 JSON `data:`，每条含 `request_id`、`message_id`、`sequence`、`created_at`。事件类型：

```text
event: message.started
data: {"request_id":"...","message_id":"...","sequence":1,"created_at":"..."}

event: retrieval.completed
data: {"message_id":"...","sequence":2,"candidate_count":20,"selected_count":5,"took_ms":86}

event: message.delta
data: {"message_id":"...","sequence":3,"delta":"根据 2026 版差旅制度，"}

event: citation
data: {"message_id":"...","sequence":4,"citation":{"id":"...","ordinal":1,"document_title":"差旅管理制度","version":3,"page_from":8,"page_to":8,"quote":"住宿费标准按城市等级执行……"}}

event: usage
data: {"message_id":"...","sequence":5,"input_tokens":1820,"output_tokens":210,"estimated":false}

event: message.completed
data: {"message_id":"...","sequence":6,"finish_reason":"stop","trace_id":"..."}
```

错误分两类：

- 建立流之前的错误使用普通 HTTP 状态 + `application/problem+json`。
- 建立流之后的错误发送 `event: error`，数据包含稳定 `code`、安全 `message`、`retryable`，随后关闭流；HTTP 状态仍可能是 200。

SSE 约束：

- `sequence` 单调递增，客户端据此去重；服务端每 15 秒发送注释心跳 `: keep-alive`。
- 网关 idle timeout 大于心跳间隔；Pod 终止先停止接收新流，再给活动请求优雅结束窗口。
- 不承诺在浏览器断线后从 token 级续传；客户端可查询最终消息。若未来支持恢复，使用 `Last-Event-ID` 和短期事件缓冲并单独版本化。
- `citation` 事件中的 `quote` 限长且已经鉴权；打开完整原文时再次鉴权。

## 5. 创建文档与预签名上传

`POST /api/v1/knowledge-bases/{kb_id}/documents`

Headers：`Idempotency-Key: <128 chars max>`

```json
{
  "title": "差旅管理制度",
  "filename": "travel-policy-v3.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 2480031,
  "sha256": "13f4...64-hex...9a2c",
  "classification": "internal",
  "acl": [
    {"principal_type": "group", "principal_id": "0190f7...", "permission": "read"}
  ],
  "metadata": {"department": "finance", "effective_date": "2026-07-01"}
}
```

响应 `201`：

```json
{
  "document_id": "0190f710-9d8f-7f21-8a33-178959fe019b",
  "version_id": "0190f711-0ed2-7a11-b126-86f750fdc93c",
  "status": "uploading",
  "upload": {
    "method": "PUT",
    "url": "https://object.example.com/presigned/...",
    "expires_at": "2026-07-15T02:30:00Z",
    "required_headers": {"content-type": "application/pdf"}
  }
}
```

预签名 URL 短期有效且仅允许指定 key、大小与方法。上传后调用：

`POST /api/v1/documents/{document_id}/upload-complete`

```json
{"version_id":"0190f711-0ed2-7a11-b126-86f750fdc93c","sha256":"13f4...9a2c"}
```

响应 `202`：

```json
{"document_id":"...","job_id":"0190f715-a12c-70e8-97fd-4bd797503a48","status":"pending","stage":"scan"}
```

服务端必须 HEAD/读取对象确认实际大小和 hash，不可仅信任完成请求。对象在扫描通过前处于 quarantine 前缀/桶。

## 6. 任务查询

`GET /api/v1/jobs/{job_id}`

```json
{
  "id": "0190f715-a12c-70e8-97fd-4bd797503a48",
  "resource_type": "document_version",
  "resource_id": "0190f711-0ed2-7a11-b126-86f750fdc93c",
  "status": "running",
  "stage": "embedding",
  "progress": 72.5,
  "attempt": 1,
  "max_attempts": 3,
  "metrics": {"pages": 36, "chunks_total": 182, "chunks_completed": 132},
  "error": null,
  "created_at": "2026-07-15T02:21:00Z",
  "updated_at": "2026-07-15T02:22:18Z"
}
```

失败时 `error` 为 `{"code":"PARSER_UNSUPPORTED_LAYOUT","message":"无法稳定解析该版式，请转换为可搜索 PDF 后重试","retryable":false}`，不返回堆栈和内部路径。

## 7. 检索调试接口

`POST /api/v1/retrieval/search`（管理员或获授权开发调用，生产默认限流）

```json
{
  "query": "住宿费标准",
  "knowledge_base_ids": ["0190f6dd-49ab-7a17-9a10-84f3e23f65cc"],
  "top_k": 5,
  "include_content": true,
  "filters": {"department": ["finance"], "effective_at": "2026-07-15"}
}
```

响应中的每个 hit：

```json
{
  "chunk_id": "...",
  "document_id": "...",
  "document_version_id": "...",
  "document_title": "差旅管理制度",
  "page_from": 8,
  "section_path": ["住宿管理", "报销标准"],
  "content": "……",
  "scores": {"vector": 0.82, "keyword": 0.71, "rerank": 0.91},
  "metadata": {"department": "finance", "effective_date": "2026-07-01"}
}
```

`include_content=false` 时不返回正文。过滤字段由知识库 schema 白名单定义，禁止客户端传任意 SQL/表达式。即使是调试接口也必须执行相同 ACL。

## 8. 反馈接口

`POST /api/v1/messages/{message_id}/feedback`

```json
{
  "rating": -1,
  "reason_code": "incorrect_citation",
  "comment": "引用页码正确，但答案把二线城市写成了一线城市。"
}
```

| 字段 | 规则 |
|---|---|
| `rating` | `-1` 或 `1` |
| `reason_code` | `helpful/incorrect/factually_unsupported/incorrect_citation/outdated/unsafe/other` |
| `comment` | 可选，≤ 2000 字符；按敏感信息规则处理 |

同一用户同一消息只有一个当前反馈，重复提交为 upsert 并保留审计历史。

## 9. 错误模型

使用 `application/problem+json`：

```json
{
  "type": "https://qa.example.com/problems/quota-exceeded",
  "title": "Quota exceeded",
  "status": 429,
  "code": "QUOTA_EXCEEDED",
  "detail": "今日问答额度已用完，请联系租户管理员。",
  "instance": "/api/v1/chat/completions",
  "request_id": "0190f720-...",
  "retryable": false,
  "errors": []
}
```

| HTTP | Code | 场景 | 是否重试 |
|---:|---|---|---|
| 400 | `VALIDATION_ERROR` | 字段或业务校验失败 | 修改请求后 |
| 401 | `UNAUTHENTICATED` | Token 无效/过期 | 重新认证 |
| 403 | `FORBIDDEN` | 无操作权限 | 否；不要透露资源存在性 |
| 404 | `RESOURCE_NOT_FOUND` | 不存在或无权查看的资源 | 否 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同 key 不同请求 | 使用新 key |
| 409 | `INVALID_STATE_TRANSITION` | 非法状态流转 | 查询最新状态 |
| 412 | `VERSION_CONFLICT` | ETag 不匹配 | 读取后合并 |
| 413 | `FILE_TOO_LARGE` | 超过租户/系统限制 | 减小文件 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 类型不允许 | 转换文件 |
| 422 | `CONTENT_REJECTED` | 病毒/安全策略拒绝 | 否 |
| 429 | `RATE_LIMITED` | 短时限流 | 按 Retry-After |
| 429 | `QUOTA_EXCEEDED` | 预算/额度耗尽 | 否 |
| 502 | `MODEL_PROVIDER_ERROR` | 上游不可用且无降级 | 可，有限次数 |
| 503 | `SERVICE_UNAVAILABLE` | 平台暂不可用 | 可，指数退避 |
| 504 | `MODEL_TIMEOUT` | 模型超时 | 可，按策略 |

## 10. Webhook/领域事件

对外 Webhook（如 `document.ready`、`document.failed`、`evaluation.completed`）采用 HTTPS POST：

```json
{
  "id": "evt_0190f7...",
  "type": "document.ready",
  "version": 1,
  "tenant_id": "0190f6...",
  "occurred_at": "2026-07-15T02:26:18Z",
  "data": {"document_id":"...","version_id":"...","job_id":"..."}
}
```

Headers：`X-QA-Event-Id`、`X-QA-Timestamp`、`X-QA-Signature: v1=<HMAC-SHA256>`。签名内容为 `timestamp + "." + raw_body`；消费者校验时间窗口并按 event ID 幂等。发送端指数退避，超过上限进入死信并告警。内部事件遵循相同 envelope，但不对 payload 暴露密钥或正文。

## 11. API 演进与契约测试

- 兼容变更：新增可选请求字段、响应字段、枚举需确认客户端对未知值容忍；枚举新增在部分客户端上可能是不兼容变更，需契约测试。
- 不兼容变更：删除/改名/改变语义/提高必填要求，进入新主版本并提供迁移期。
- OpenAPI 在 CI 中 lint，生成服务端/客户端类型或至少用于 contract test；实现不得手工漂移。
- 消费者驱动契约覆盖 Web、服务账号 SDK 和主要集成方；预生产部署前验证。
- 字段弃用在 schema 中标 `deprecated`，文档给出替代项和停止支持日期。

可执行接口骨架见 [openapi.yaml](openapi.yaml)。

