# S3 测试与验证报告

> 执行日期：2026-07-16  
> 范围：合成本地环境、干净容器构建、真实 PostgreSQL/Redis/MinIO 隔离验收栈  
> 注意：本报告不等价于真实文档 UAT、渗透测试、性能测试或生产批准。

## 1. 自动化覆盖

| 层次 | 覆盖内容 |
|---|---|
| Unit | PDF/DOCX/TXT/MD 统一解析；MIME 欺骗；恶意标记；ClamAV INSTREAM 正常/检出/协议错误/超时；结构分块；Fake Embedding 确定性/归一化；本地签名上传防篡改 |
| Integration | KB/文档/预签名/PUT/completion/Worker/job/detail/search 全链路；completion 幂等；tenant/ACL；版本原子切换；SHA 失败；retry 前置与幂等 |
| Regression | S1 身份/租户/会话/BFF 契约；S2 Gateway/SSE/重试/取消/usage 不回退 |
| Static | Ruff；Mypy strict；ESLint/TypeScript |
| Migration | SQLite 从空库 up 到 S3、down 到 S2、再 up S3；全栈 PostgreSQL migration 到 `20260716_0003` |
| Contract | 8 个 YAML 可解析；157 个 OpenAPI 内部 `$ref` 可解析；19 个路径受脚本断言 |
| Supply chain | Python lock audit、npm audit；API/Worker/Web 干净镜像构建；Compose 配置解析 |

## 2. 最终执行记录

| 检查 | 结果 |
|---|---|
| `pytest -q --cov=...` | 45 tests passed；总覆盖率 86%，ingestion 88% |
| `ruff check apps tests scripts` | passed |
| `mypy apps/api/src apps/worker/src` strict | passed，18 source files |
| `alembic up → down 0002 → up` | passed，revision `20260716_0003` |
| `npm run lint` | passed |
| 本机 `npm run build` | 未强停用户已有 Next dev 进程；其锁定 `.next/trace` |
| API/Worker/Web 干净容器构建 | passed；Web 在容器中完成编译、TypeScript 和静态页面生成 |
| `scripts/validate_contracts.py` | passed；8 YAML、157 refs、19 paths |
| `docker compose config --quiet` | passed |
| Python `pip-audit --no-deps` | 0 known vulnerabilities；锁文件当前未带哈希，作为供应链开放项 |
| npm production audit | 0 known vulnerabilities |
| Helm 静态复核 | values/configmap/deployment/secret 引用已对齐；本机未安装 Helm CLI，未形成 lint/install 证据 |
| Compose PostgreSQL/Redis/MinIO smoke | passed；OIDC 登录、签名直传、Worker 入库、任务轮询、ACL 调试检索完整成功 |

全栈 smoke 生成的资源 ID 只用于合成验收，不是长期环境标识。验收日志显示 Worker 完成相同 job，API 创建/完成/轮询/检索均返回预期状态且无隐藏错误。证据保存后，`enterprise-qa-s3-smoke` 专用容器、网络和合成数据卷已安全删除；未删除镜像，也未改动历史 `enterprise-qa` 数据卷。

## 3. 全栈验收发现与修复

1. SQLite 测试没有暴露 `document_acls` 写入先于 `documents` 的 ORM flush 排序问题；真实 PostgreSQL 外键拒绝了首次写入。服务在创建 document/version 后显式 flush，再创建 ACL，重建镜像后通过。
2. MinIO/API 只连接 Docker `internal` 网络时，Docker Desktop 26.1.1 保留 HostConfig 绑定但不创建宿主机端口转发。Compose 保留内部 backend 服务发现，同时把需要本机入口的 API/MinIO 加入 non-internal frontend 网络；端口仍只绑定 `127.0.0.1`。
3. 上述问题证明 SQLite 和静态 Compose 解析不能替代真实 PostgreSQL、对象存储与浏览器直传验收。S3 及以后阶段必须保留隔离全栈 smoke 门禁。

## 4. 关键安全断言

1. 客户端不能指定 tenant 或物理对象键。
2. MIME/size/hash/恶意内容失败均不产生 active chunk/current version。
3. 另一 tenant 即使使用相同 role code，也无法读取文档或检索 chunk。
4. ACL 是 SQL 候选集条件，不是 top-k 后处理。
5. 新版本发布前 v1 仍可检索，发布后只有 v2 active。
6. duplicate completion/retry 不创建重复逻辑任务。
7. production 配置拒绝 local object store、Fake model/embedding、签名扫描器、HTTP 外部 endpoint、应用自动建 bucket/schema。
8. API 响应不包含 bucket/key/vector/密钥/扫描器原始结果。

## 5. 尚未形成的证据

- 真实 PDF/DOCX 版式、中文表格、扫描件/OCR 的业务 UAT。
- 多 Worker PostgreSQL `SKIP LOCKED` 竞争、lease 续租和崩溃风暴。
- 真实 S3 IAM/KMS/versioning/lifecycle、ClamAV 集群和外部 Embedding。
- 目标吞吐、文件大小分布、解析 P95、队列延迟、成本和容量。
- Helm lint/Kubernetes 安装、NetworkPolicy、Ingress、Secret Manager、滚动发布。
- 恶意文件 fuzz、Zip/XML/PDF 资源耗尽、渗透和 DLP 扫描。

这些项在 `06-risks-and-open-items.md` 中仍是生产阻断，不能由当前 45 个合成测试替代。
