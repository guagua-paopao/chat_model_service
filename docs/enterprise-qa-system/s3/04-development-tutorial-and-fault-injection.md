# S3 开发教学与故障注入

## 1. 学习目标

完成本教程后，工程师应能解释：为什么大文件走预签名数据面、为什么文件声明必须重验、为什么 chunk 要 staged、为什么 ACL 必须先于 top-k、为什么对象复制与数据库发布不能假装是一个分布式事务，以及怎样用 job 租约和幂等键恢复崩溃。

## 2. 本地准备

```powershell
Copy-Item .env.example .env
docker compose -f infra/compose/compose.yaml config
docker compose -f infra/compose/compose.yaml up --build
```

浏览器打开 `http://127.0.0.1:3000`，开发 OIDC 登录。先点击“新建演示知识库”，选择 `.md/.txt/.docx/.pdf`，上传并观察进度。MinIO 控制台仅用于本地教学，不应把 root 凭据用于生产。

本机不使用 Compose 时：

```powershell
.venv\Scripts\uvicorn.exe qa_api.main:app --app-dir apps/api/src --reload
```

默认 local object store 位于 `.local/objects`，API 返回 HMAC 签名 PUT 路径；Worker 可在另一个终端运行：

```powershell
$env:PYTHONPATH="apps/api/src;apps/worker/src"
.venv\Scripts\python.exe -m qa_worker.main
```

## 3. 从零实现顺序

1. 先定义 `document/version/acl/chunk/job/outbox` 状态与唯一约束，再写接口。
2. 抽象 ObjectStore，先写 local 签名实现与 tamper/path 测试，再接 S3。
3. 只实现 completion 入队，不在 API 请求中解析；验证重复 completion 返回同 job。
4. 写纯函数 parser/chunker，使用四格式合成 fixture，不依赖数据库。
5. 写 Fake Embedding，使测试可重复；再写外部 Adapter 和安全错误归一化。
6. 写 Worker claim/lease/progress/failure；在任何发布前只写 staged。
7. 写单事务 publish，然后写“旧版本仍 active”集成测试。
8. 最后写 debug retrieval，先构造 SQL ACL 候选集，再评分。
9. UI 只展示实际能力，并固定提示“不接聊天”。
10. 更新 OpenAPI、迁移、Compose、Helm、ADR、风险和 Gate。

每一步都先写失败测试。把“能演示”与“可恢复、可审计、不可越权”分开验收。

## 4. API 手工流程

取得登录 token 后：

```text
POST /api/v1/knowledge-bases
POST /api/v1/knowledge-bases/{kb}/documents
PUT  {upload_url}  Content-Type: {upload_headers.Content-Type}
POST /api/v1/documents/{document}/upload-complete
GET  /api/v1/ingestion-jobs/{job}
POST /api/v1/retrieval/search
```

不要把 upload URL 复制进工单或日志；它在有效期内相当于单对象写能力。客户端 SHA 计算是体验和早期发现机制，Worker 重算才是信任事实。

## 5. 调试检查点

| 阶段 | 检查 |
|---|---|
| awaiting_upload | document/version/ACL 已存在；quarantine 可为空；published 空 |
| queued | 对象 HEAD size 匹配；job/outbox 在同一提交 |
| scanning | attempt 已增加；lease_owner/until 设置；无 published chunk |
| parsing/chunking | 错误只含安全消息；parser 不落地任意 ZIP 路径 |
| embedding | 批大小、模型/维数、分类路由正确；无跨 tenant hash reuse |
| publishing | staged chunks inactive；对象先复制，DB 后切换 |
| completed | current_version 指向新版本；新 chunks active；旧 chunks archived；quarantine 尽力删除 |

## 6. 故障注入实验

### 6.1 MIME 欺骗

把纯文本命名为 `.pdf` 并声明 PDF。预期 completion 可创建 job，但 Worker 在 scanning 返回 `MIME_TYPE_MISMATCH`，published 无对象，document 无 current version。

### 6.2 哈希被替换

声明 A 的 SHA/size，上传同长度 B。预期 API size 早检通过，Worker 重算后 `SHA256_MISMATCH`。这说明 HEAD/客户端 hash 不能替代服务端内容校验。

### 6.3 恶意样本

只在隔离测试环境上传 EICAR 或 `[MALWARE]` 合成字符串。预期 `MALWARE_DETECTED`、不可自动重试。不要在共享或生产环境随意投放安全样本。

### 6.4 Embedding 暂时失败

用 MockTransport 让 `/embeddings` 先 429/timeout 后成功。观察 attempt、available_at 指数退避、重复 staged 清理和最终一次发布。把 max attempts 设为 2，持续失败应进入 dead_letter。

### 6.5 Worker 崩溃

在 staged chunks 写入后、对象复制前终止 Worker。等待 lease 过期并重启。预期同 version 的 inactive staged chunks 被替换，不出现两个 active version。

### 6.6 对象复制后 DB 失败

在 copy 后注入 DB commit 异常。预期 published bucket 可能出现 orphan object，但 DB 不可检索。记录 object reconciliation backlog；不要用“对象存在”判断发布成功。

### 6.7 ACL 错序反例

先做全局 top-k 再过滤 ACL，构造一个高相关但无权文档和一个低相关有权文档，会造成召回损失，且分数/计时可能泄露。恢复为 SQL EXISTS ACL 内候选集，再运行跨 tenant/user/role 矩阵。

### 6.8 新版本原子切换

发布 v1，创建并上传 v2，在 v2 worker 尚未执行时检索只能看到 v1；完成后只能看到 v2。任何中间状态同时看到两版都属于 P0 数据一致性问题。

## 7. 常见排障

| 现象 | 原因/动作 |
|---|---|
| 浏览器 PUT 403 | URL 过期、Content-Type 与签名不一致、MinIO CORS/origin；重新创建版本，不手改 URL |
| completion 409 object not found | PUT 尚未完成或网络失败；确认上传响应后重试 |
| job 长期 queued | Worker 未启动、DB 连接、available_at/时钟；查看结构化 worker 事件 |
| job 重复 running | lease 过短或任务耗时长；生产需续租/阶段超时完善 |
| DOCX parse failed | 文件并非 OOXML、损坏或缺必要 member；用 Office 重新保存 |
| PDF empty | 扫描图片无文本；S3 不支持 OCR，进入后续能力评审 |
| debug search 空 | 未 completed、ACL 不匹配、查询无词项重叠、选错 KB；按顺序查状态和 ACL |
| production 启动失败 | Fake/local/signature scanner 或 HTTP endpoint 被 fail-fast；配置批准的 S3/Embedding/ClamAV/Secret |

## 8. 提交前清单

```powershell
.venv\Scripts\pytest.exe --cov=qa_api --cov-report=term-missing
.venv\Scripts\ruff.exe check apps tests
.venv\Scripts\mypy.exe apps/api/src apps/worker/src
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run build
.venv\Scripts\python.exe -m pip_audit -r requirements.lock
npm.cmd --prefix apps/web audit --omit=dev
```

再执行迁移 up/down/up、Compose 配置解析、镜像构建和端到端上传 smoke。若本机已有 Next dev server 锁定 `.next/trace`，不要强停用户进程；在干净容器构建作为可复验证据，并在报告中记录本机限制。

