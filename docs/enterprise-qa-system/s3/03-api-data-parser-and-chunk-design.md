# S3 API、数据、解析与分块设计

## 1. 通用约定

- 基础路径 `/api/v1`；认证使用 Bearer token，经 BFF 时同时执行 CSRF。
- tenant 不出现在请求 body；从认证身份解析。
- UUID 使用 UUIDv7；时间为 UTC RFC 3339；SHA-256 为 64 位小写十六进制。
- 错误使用 `application/problem+json` 风格字段：`type,title,status,code,detail,request_id,retryable`。
- filename 只允许文件名，不允许 `/`、`\` 或控制字符。
- 当前允许 MIME：`application/pdf`、DOCX MIME、`text/plain`、`text/markdown`。

## 2. 端点与主要字段

### 2.1 知识库

`POST /knowledge-bases`

```json
{
  "code": "travel_policy",
  "name": "差旅制度",
  "description": "合成演示资料",
  "classification": "internal"
}
```

code tenant 内唯一；状态初始 `active`。`GET /knowledge-bases` 只返回当前 tenant 的 active 条目。

### 2.2 创建文档与首版本

`POST /knowledge-bases/{kb_id}/documents`

| 字段 | 类型/限制 | 语义 |
|---|---|---|
| title | string 1..300 | 管理显示名 |
| filename | string 1..255 | 原始文件名元数据，不是路径 |
| mime_type | enum | 客户声明，Worker 重新检测 |
| size_bytes | 1..100 MiB，运行配置默认 10 MiB | 客户声明，完成时 HEAD、Worker 再校验 |
| sha256 | lowercase hex64 | 客户声明，Worker 重算 |
| classification | public/internal/confidential/restricted | 不得低于 KB 分类 |
| acl | 1..100 | `{subject_type,user/group/role; subject_id; permission=read}` |
| metadata | object，最多 20 键 | 安全业务元数据，不放正文/密钥 |

响应包含 `document_id`、完整 `version`、`upload_url/method/headers/expires_at`。预签名 URL 属敏感短期能力，不写普通日志。

`POST /documents/{document_id}/versions` 只接收 filename/MIME/size/SHA，沿用 document 分类、ACL、title 和 metadata；如果最新版本仍 awaiting/queued/processing 返回 409。

### 2.3 上传完成

`POST /documents/{document_id}/upload-complete`

```json
{"version_id":"...","sha256":"..."}
```

服务核对 version 归属、声明 hash 和对象 size，写入幂等 job/outbox，返回 202 Job。重复相同 version/hash 返回原 job。

### 2.4 查询与重试任务

`GET /ingestion-jobs/{id}` 返回：

| 字段 | 说明 |
|---|---|
| id/document_id/version_id | 因果关系 |
| status | queued/running/completed/failed/dead_letter |
| stage | queued/scanning/parsing/chunking/embedding/publishing/completed |
| progress | 0..100，阶段性进度，不承诺精确剩余时间 |
| attempt/max_attempts | 当前领取次数和上限 |
| metrics | chunks/tokens/model/retry_of 等安全指标 |
| error_code/error_detail | 稳定机器码和安全操作提示，不含堆栈/正文 |
| created_at/updated_at/completed_at | 生命周期 |

`POST /ingestion-jobs/{id}/retry` 仅接受 failed/dead_letter，必须有 1..128 字符 `Idempotency-Key`，返回新 job；相同键返回同一新 job。

### 2.5 文档详情

`GET /documents/{id}` 返回 document、ACL、按 version_no 倒序的不可变版本和 latest_job。物理 bucket/key、embedding vector、签名 URL 和安全扫描原始输出不返回。

### 2.6 调试检索

`POST /retrieval/search`

```json
{
  "query": "报销需要什么凭证",
  "kb_ids": ["..."],
  "top_k": 5,
  "include_content": true,
  "filters": {"classification": "internal"}
}
```

响应 `items` 含 chunk/document/version/title/score/page/section/content；`acl_filtered=true`；`stage=debug_only_not_connected_to_chat`。不支持的 filter 返回 422，而不是静默忽略。

## 3. 稳定错误码

| code | HTTP/任务状态 | 操作建议 |
|---|---|---|
| `KNOWLEDGE_BASE_CODE_EXISTS` | 409 | 换 code 或查询现有 KB |
| `CLASSIFICATION_DOWNGRADE_FORBIDDEN` | 422 | 提高 document 分类 |
| `UPLOAD_TOO_LARGE` | 413 | 压缩/拆分或按审批调整限额 |
| `UPLOAD_GRANT_INVALID/SCOPE_INVALID` | 400 | 重新创建版本/预签名 |
| `OBJECT_NOT_FOUND` | 409 | 确认 PUT 成功后重试 completion |
| `UPLOAD_SIZE_MISMATCH` | 422/failed | 重新上传新版本 |
| `SHA256_DECLARATION_MISMATCH` | 422 | 修正 completion 参数 |
| `SHA256_MISMATCH` | failed | 文件被替换/传输错误；新版本重传 |
| `MIME_TYPE_MISMATCH` | failed | 使用正确格式/MIME |
| `MALWARE_DETECTED` | failed | 隔离并按安全流程调查，不自动重试 |
| `MALWARE_SCANNER_UNAVAILABLE` | queued/dead_letter | 检查 ClamAV，恢复后重试 |
| `PDF_ENCRYPTED/PDF_PARSE_FAILED/DOCX_PARSE_FAILED` | failed | 解密/修复源文件后创建新版本 |
| `TEXT_ENCODING_INVALID/DOCUMENT_EMPTY` | failed | 转 UTF-8/补充可提取正文 |
| `EMBEDDING_ROUTE_FORBIDDEN` | failed | 使用私有批准路由或降低不了的分类保持阻断 |
| `EMBEDDING_*` | queued/failed/dead_letter | 按 retryable 和 attempt 处理 |
| `IDEMPOTENCY_KEY_REQUIRED/INVALID` | 428/400 | 提供稳定业务键 |

## 4. 数据表

| 表 | 核心字段/约束 |
|---|---|
| knowledge_bases | tenant+code unique；classification/status/created_by |
| documents | tenant+kb FK；classification/status/current_version_id/metadata |
| document_versions | tenant+document+version_no unique；声明/事实 hash,size,MIME；对象位置；parser/chunker/embed provenance；计数 |
| document_acl | tenant+document+subject+permission unique；user/group/role/read |
| document_chunks | tenant+version+index unique；content/hash/token/page/section/embedding/status/is_active |
| ingestion_jobs | tenant+idempotency unique；status/stage/progress/attempt/lease/metrics/safe error/request/trace |
| outbox_events | aggregate/event/payload/status/attempt/available/published |
| audit_logs | actor/action/resource/result/request/trace/details_safe |

所有 Repository/Service 读写均显式 tenant scope。S3 embedding 暂存 JSON 向量，便于 Fake 测试；S4 引入 pgvector 索引迁移和 hybrid 检索，不能把当前词项调试排序当生产检索。

## 5. 统一解析模型

```text
ParsedDocument(detected_mime_type, page_count, elements[])
ParsedElement(element_type, text, page, section_path[], metadata{})
```

| 格式 | 结构映射 | 限制 |
|---|---|---|
| TXT | 空行分段为 paragraph | UTF-8；无 page/section |
| MD | `#..######` 更新 section path；正文 paragraph | 不渲染 HTML，不执行链接/指令 |
| DOCX | WordprocessingML paragraph/HeadingN | 不支持宏、图片 OCR、复杂表格语义 |
| PDF | 每页 extract_text 后 paragraph | 加密/空/损坏拒绝；扫描 PDF 不 OCR |

Parser version 固定 `unified-parser-s3-v1`。变更文本规范化、结构映射或库主版本时必须递增并重建版本，而不是原地改 chunk。

## 6. 分块算法

1. 按解析元素遍历；标题/段落和 section path 是第一边界。
2. 单元素超过 `max_tokens` 时按最大字符窗口拆分，使用 overlap。
3. 相邻、同 section、合并后不超限的元素合并。
4. 生成 index/content/content_hash/token_count/page_from/to/section_path/element_type。
5. token 估算当前为 `ceil(characters/4)`，只用于 S3 分块教学；S4 必须按目标 embedding/chat tokenizer 校准。

默认 max=256、overlap=32；测试使用 64/8 暴露边界。Chunker version 固定 `structure-chunker-s3-v1`。

## 7. Embedding 契约

```python
class EmbeddingAdapter(Protocol):
    model_code: str
    version: str
    dimensions: int
    external: bool
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- Fake 使用 SHA-256 扩展并 L2 归一化，确定性但没有语义质量，只允许 local/test/dev。
- OpenAI-compatible 调用 `/embeddings`，按 index 排序，严格校验条数和维数，归一化 429/超时/协议错误。
- 每批 32；同 tenant/model/hash/维数复用；不跨 tenant。
- 版本保存 model/version/dimensions。真实路由必须完成数据区域、保留、DPA、成本和分类审批。

