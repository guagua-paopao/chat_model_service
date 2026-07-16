# S3 需求与范围

## 1. 阶段目标

把受控文件转换为“可追溯、可授权、可原子切换的检索分块”，让知识管理员能看到每一步状态、错误与恢复动作，并为 S4 RAG 闭环提供安全输入面。

S3 完成的是摄取和调试检索，不完成聊天接入。任何 `grounded_answer`、`search_only` 或携带知识库 ID 的聊天请求仍返回 `409 KNOWLEDGE_NOT_CONNECTED_IN_S3`。

## 2. 角色与应用场景

| 角色 | 场景 | 需要的权限 |
|---|---|---|
| 知识管理员 | 建知识库、上传文件、建新版本、看状态、重试失败任务 | `qa:knowledge:write/read`、`qa:ingestion:read/retry` |
| 普通员工 | S3 不直接开放知识管理；S4 才消费授权检索 | `qa:ask` |
| Worker 服务账号 | 从 DB 领取任务，访问隔离/发布 bucket，写版本和 chunk 状态 | 最小数据库与对象存储权限 |
| 安全/审计 | 复核分类、ACL、扫描失败和发布审计 | 后续 S5 管理界面；S3 保留审计记录 |

主要演示场景：

1. 上传合成差旅制度 Markdown，处理完成后按“报销凭证”检索。
2. 上传新版本，处理期间旧版本继续服务；新版本完成后一次性切换。
3. 上传伪 PDF、错误 SHA、EICAR/`[MALWARE]` 测试样本，确认失败且不发布。
4. 使用另一 tenant 或不匹配 ACL 的 principal 检索，结果为空或资源不可见。
5. 对失败任务使用 `Idempotency-Key` 重试，重复提交得到同一个 retry job。

## 3. 功能需求

| ID | 优先级 | 需求 | 验收 |
|---|---|---|---|
| S3-F-001 | Must | 创建/列出 tenant 内知识库 | code tenant 内唯一；分类不可伪造 tenant |
| S3-F-002 | Must | 创建文档和不可变版本 | version_no 单调；旧版本字段不覆盖 |
| S3-F-003 | Must | 返回有限期预签名 PUT | URL 过期、范围绑定、bucket/对象键不可由客户端决定 |
| S3-F-004 | Must | quarantine/published 隔离 | 两 bucket 不得相同；校验前 published 无对象 |
| S3-F-005 | Must | 校验大小/SHA/MIME/恶意内容 | 任一失败为安全错误码，版本不发布 |
| S3-F-006 | Must | PDF/DOCX/TXT/MD 统一解析 | 输出 element type、text、page、section path、metadata |
| S3-F-007 | Must | 结构优先分块 | 尊重标题/段落，限制 token，保留页码/章节/哈希 |
| S3-F-008 | Must | 批量 Embedding、重试与 hash reuse | 每批不超过 32；同 tenant/模型/内容哈希可复用 |
| S3-F-009 | Must | 独立 Worker 与租约领取 | 任务可重领；attempt、lease、进度、错误可查 |
| S3-F-010 | Must | staged → published 原子切换 | 任何时刻至多一个版本的 chunks active |
| S3-F-011 | Must | ACL 在评分前过滤 | tenant、active、published、user/role ACL 均在 SQL 候选集约束中 |
| S3-F-012 | Must | 管理 UI 展示进度、错误、重试基础 | 浏览器能上传、轮询、显示 stage/progress/error |
| S3-F-013 | Must | 审计与 outbox | 创建、完成、重试、发布写审计；任务事件可追踪 |
| S3-F-014 | Should | ClamAV 生产 Adapter | INSTREAM；不可用可重试；命中不可重试 |
| S3-F-015 | Should | S3/MinIO 与本地存储 Adapter | 领域服务只依赖 ObjectStore Protocol |

## 4. API 范围

- `POST/GET /api/v1/knowledge-bases`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/documents/{document_id}/versions`
- `PUT /api/v1/uploads/{version_id}/content?token=...`（仅本地 Adapter；S3 返回直接 URL）
- `POST /api/v1/documents/{document_id}/upload-complete`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/ingestion-jobs/{job_id}`
- `POST /api/v1/ingestion-jobs/{job_id}/retry`
- `POST /api/v1/retrieval/search`

请求/响应字段与错误码见 `03-api-data-parser-and-chunk-design.md`，机器契约见上级 `openapi.yaml`。

## 5. 非功能需求

| 类别 | S3 要求 |
|---|---|
| 安全 | tenant 来源于验证 token；路径不可遍历；日志不记录正文、token、密钥；外部 Embedding 禁止 confidential/restricted |
| 一致性 | completion 幂等；retry 显式幂等；chunk 发布在 DB 单事务；版本不可变 |
| 容错 | lease 过期可重领；可重试错误指数退避；耗尽进入 dead_letter |
| 可维护性 | parser/chunker/embedding 版本写入 document_version；供应商 SDK 不进入领域层 |
| 性能基线 | 单文件默认 10 MiB；最多 100 MiB 配置上限；Embedding 每批 32；本阶段不宣称生产吞吐 SLO |
| 可观察性 | job stage/progress/attempt/metrics/error、request_id/trace_id、审计、结构化 Worker 事件 |
| 供应链 | 锁定依赖；Python/npm audit；容器非 root；Helm Secret 引用 |

## 6. 状态机和验收

文档版本：`awaiting_upload → queued → processing → published`；不可恢复校验失败进入 `failed`。  
任务：`queued → running → completed`；可重试失败回到 `queued`，不可重试为 `failed`，重试耗尽为 `dead_letter`。  
阶段：`queued/scanning/parsing/chunking/embedding/publishing/completed`。

Definition of Done：

- 四格式主路径和 MIME/恶意/哈希失败路径有自动化测试。
- 完成请求幂等、手工重试幂等、租户/ACL 隔离和版本原子切换有集成测试。
- 迁移执行 `up → down to S2 → up`。
- API、Worker、Web、Compose、Helm、OpenAPI 与文档一致。
- Gate 明确真实数据、真实供应商、Kubernetes、性能和生产扫描的阻断项。

## 7. 明确非目标

- 不做聊天 RAG、hybrid search、rerank、context packing、引用、拒答质量评估。
- 不做 OCR、图片/扫描件、复杂表格还原、旧版 `.doc`、Excel/PPT、网页连接器。
- 不做 group claim/SCIM 同步；group ACL 当前 fail closed。
- 不做文档在线编辑、删除/保留策略 UI、审批流、法律保全。
- 不用合成测试结果证明真实业务准确率、成本、SLO 或生产安全批准。

