# S3 安全文档摄取与调试检索证据包

> 版本：s3-v1.0  
> 日期：2026-07-16  
> 数据边界：仅限合成、公开或明确批准的非敏感资料  
> 结论：S3 功能门禁通过；只授权进入 S4 合成 RAG 开发，不代表真实数据、staging 或生产上线许可。

S3 在 S1 身份/租户/BFF 和 S2 Model Gateway/SSE 基线上，实现知识库、不可变文档版本、签名直传、隔离区校验、四格式解析、结构优先分块、Embedding Adapter、异步 Worker、原子发布、ACL 前置过滤和调试检索。聊天仍明确拒绝 `grounded_answer/search_only`，不会把调试检索伪装成有依据问答。

最终证据：45 tests、86% 总覆盖率、静态/契约/迁移/供应链门禁通过，API/Worker/Web 干净容器构建通过，PostgreSQL/Redis/MinIO/OIDC/签名直传/Worker/ACL 调试检索全栈 smoke 通过。生产限制见 Gate 与风险清单。

## 文档导航

| 文档 | 目的 |
|---|---|
| [需求与范围](01-s3-requirements-and-scope.md) | 场景、角色、功能/非功能需求、验收与非目标 |
| [架构与安全设计](02-ingestion-architecture-and-security.md) | 信任边界、状态机、失败模型、ACL、原子发布与部署 |
| [API、数据、解析与分块设计](03-api-data-parser-and-chunk-design.md) | 接口、字段、表、解析器、分块器、Embedding 约定 |
| [开发教学与故障注入](04-development-tutorial-and-fault-injection.md) | 本地操作、从零开发顺序、调试、失败恢复实验 |
| [测试与验证报告](05-test-and-verification-report.md) | 自动化、迁移、前端、供应链与全栈证据 |
| [风险与开放项](06-risks-and-open-items.md) | 生产阻断、Owner、退出条件与残余风险 |
| [S3 Gate 评审](07-s3-gate-review.md) | 逐条退出条件和 S4 授权边界 |
| [决策日志](decision-log.md) | 重要决策、理由、ADR、复审触发器 |
| [机器清单](manifest.yaml) | 阶段版本、能力、验证证据和禁止事项 |

## 可执行产物

- API/编排：`apps/api/src/qa_api/ingestion.py`、`main.py`。
- 对象存储：`apps/api/src/qa_api/object_store.py`，支持本地签名存储和 S3/MinIO 预签名 PUT。
- Embedding：`apps/api/src/qa_api/embedding.py`，支持确定性 Fake 和 OpenAI-compatible Adapter。
- 数据模型/迁移：`persistence.py`、`20260716_0003_s3_document_ingestion.py`。
- Worker：`apps/worker/src/qa_worker/main.py`。
- Web/BFF：知识库、上传、进度、错误、调试检索和路径白名单。
- 部署：Compose 使用 PostgreSQL、MinIO、独立 Worker；Helm 以 Secret 引用对象存储和模型密钥，并要求 ClamAV。
- 测试：`tests/unit/test_ingestion.py`、`tests/integration/test_ingestion.py`。
- 契约：`docs/enterprise-qa-system/openapi.yaml`。

## 运行时边界

1. 文件名只作为元数据；物理对象键只包含服务端生成的 tenant/kb/document/version ID。
2. quarantine 与 published 必须是不同 bucket；未完成校验的对象永不进入 published。
3. 大小、SHA-256、MIME 魔数、恶意样本、解析、分块和向量化任一失败即 fail closed。
4. 新版本先产生 staged chunks；对象复制成功后，在单一数据库事务中停用旧 chunks、启用新 chunks、更新 current version 和完成 job。
5. 调试检索先在数据库中应用 tenant + published + active + ACL，再评分；不执行“全局 top-k 后 ACL”。
6. 当前身份没有可信 group claims，因此 group ACL 按 fail closed 处理；user/role ACL 可用。
7. Fake Embedding 和签名扫描器仅允许 local/test/dev；生产要求批准的 HTTPS Embedding 和外部 ClamAV。
8. S3 检索是词项重叠调试排序，不是 S4 hybrid retrieval、rerank、引用或回答证据链。

## 快速检查

```powershell
.venv\Scripts\pytest.exe -q
.venv\Scripts\ruff.exe check apps tests
.venv\Scripts\mypy.exe apps/api/src apps/worker/src
npm.cmd --prefix apps/web run lint
docker compose -f infra/compose/compose.yaml config
```

启动 Compose 后，浏览器登录，创建演示知识库，上传 PDF/DOCX/TXT/MD，观察 `queued → scanning → parsing → chunking → embedding → publishing → completed`，再使用“调试检索”验证 ACL 后的已发布内容。详细步骤见开发教学。
