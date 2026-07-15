# S1 需求与范围

## 1. 阶段目标

S1 不实现大模型回答或企业知识检索，而是建立后续每个阶段都依赖的工程纵切：代码能够持续构建；用户能够以 OIDC 登录；服务端能够建立不可由客户端伪造的租户/用户上下文；会话资源能够在租户与用户边界内完成基本生命周期；迁移、审计、观测、测试和部署骨架可执行。

## 2. 应用场景

### UC-S1-01 员工登录并确认身份

- 前置：员工在本地 Fake IdP 选择 `demo` 合成人员；生产将替换为企业 IdP。
- 主流程：Web 生成 `state` 与 PKCE → IdP 认证并返回一次性 code → BFF 换取 access token → BFF 调用 `/me`。
- 结果：页面显示用户、租户、角色与权限；access token 不进入 localStorage 或页面 JavaScript。
- 异常：state/PKCE 不匹配、code 重放、错误 issuer/audience、过期 token、未知或禁用用户均拒绝。

### UC-S1-02 创建并管理空会话

- 前置：用户具有 `qa:conversation:write`。
- 主流程：创建会话 → 获取会话/列表 → 使用 ETag 修改标题或归档 → 软删除。
- 结果：每次写操作生成审计记录，列表使用稳定签名游标。
- 安全：用户只能看到当前租户内自己创建的会话；不可见资源与不存在资源都返回 404。

### UC-S1-03 平台探测服务状态

- `live` 证明进程能够响应，不依赖外部组件。
- `ready` 证明数据库可访问；失败返回 503 并允许编排器摘流。
- Compose 与 Kubernetes 使用 readiness/liveness 配置，而不是以首页 200 代替健康检查。

### UC-S1-04 开发者验证提交

- 一条检查命令执行 Python/TypeScript 静态检查、测试、迁移往返、Web 构建、契约解析、Compose 静态校验和可选在线依赖审计。
- CI 对主干与 PR 执行同类门禁，并构建 API、Worker、Fake IdP 和 Web 镜像。

## 3. 功能需求与验收

| ID | 需求 | 验收证据 | 状态 |
|---|---|---|---|
| IAM-001 | 支持 OIDC Authorization Code + PKCE | Fake IdP 集成测试与全栈 smoke | 完成（本地） |
| IAM-002 | API 验证签名、issuer、audience、时间与必要声明 | `test_config_and_security.py`、`test_api.py` | 完成 |
| IAM-003 | 角色/权限来自服务端数据库映射 | `/me` 集成测试、身份 Repository | 完成 |
| IAM-005 | 禁用用户/租户不能访问 | 负向测试 | 完成 |
| TEN-001 | `tenant_id` 只来自可信 token | Repository 签名与跨租户测试 | 完成 |
| TEN-002 | 资源查询同时绑定租户与用户 | API/Repository 测试 | 完成 |
| QA-001-S1 | 创建与管理空会话骨架 | 会话 CRUD、游标、ETag 测试 | 完成 |
| OPS-001 | live/ready 健康检查 | API/Compose healthcheck | 完成 |
| OBS-001 | 每请求有 request/trace ID，日志不泄露 token/email | 日志安全测试 | 完成 |
| CICD-001 | lint/type/test/migration/audit/image build 自动化 | 本地验证与 workflow | 完成；远端部署待接入 |
| DEP-001 | 本地一套 Compose 启动完整依赖 | PostgreSQL 全栈冒烟 | 完成 |
| DEP-002 | 提供 Kubernetes/Helm 部署骨架 | Chart 静态审查 | 完成；集群验证待办 |

## 4. 非功能需求

- 安全：默认拒绝；生产禁止开发 JWT；密钥只通过环境/Secret 引用；错误响应使用 Problem+JSON；未知资源不暴露存在性。
- 可靠性：数据库迁移独立于 API 启动；更新使用乐观并发；容器非 root；Kubernetes 文件系统只读。
- 可维护性：Python 类型检查、严格 Pydantic 输入、契约优先、模块化单体 + Worker、依赖锁定。
- 可观测性：结构化日志字段白名单；贯穿 `request_id`、`trace_id`；写操作审计落库。
- 可复现性：精确 Python 运行依赖、npm lock、版本化镜像标签、确定性 Fake IdP 人员。
- 性能基线：S1 不做大模型吞吐承诺；会话列表最大 100 条/页，请求体默认不超过 1 MiB。

## 5. 范围边界

S1 包含：工程目录、身份与租户、系统角色、会话骨架、数据库迁移、BFF、Compose、Helm 骨架、CI 与自动化测试。

S1 明确不包含：真实企业 OIDC 配置、文档 ACL、知识上传/解析、向量检索、模型调用、SSE 回答、配额、生产告警面板、备份恢复演练、真实数据或正式上线。canonical OpenAPI 中上述未来接口只是跨阶段契约骨架，不代表 S1 已实现。

## 6. Definition of Done

1. 本地 OIDC → BFF → API → PostgreSQL 纵切可运行。
2. 认证与租户负向测试全绿，成功跨租户访问为 0。
3. 会话并发创建、签名游标与 ETag 冲突测试通过。
4. 数据库迁移至少在 SQLite 往返并在 PostgreSQL 正向执行。
5. Python 与 Web 静态检查、生产构建、依赖审计和四个镜像构建通过。
6. ADR、接口/字段、开发教学、测试报告、风险和 Gate 文档归档。
7. 无法在当前工作区验证的企业集成项明确列为条件，不伪造完成状态。

