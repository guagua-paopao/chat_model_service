# S1 测试与验证报告

> 执行日期：2026-07-15  
> 环境：Windows / Python 3.12 / Node.js 22 / Docker Desktop / PostgreSQL 16(pgvector)

## 1. 结论摘要

S1 代码级与本地全栈门禁通过：21 个 pytest 测试与 9 个子测试通过，严格 warning 模式无告警，综合覆盖率 89.66%；Ruff、Mypy、Web lint/typecheck/production build、OpenAPI 解析、SQLite 迁移 up/down/up、PostgreSQL 正向迁移、四个 Docker 镜像构建、Compose 全栈和 OIDC/BFF smoke 均通过。Python 运行依赖和 npm 依赖在线审计均为 0 个已知漏洞。

企业 OIDC、GitHub 主干自动部署到真实 dev、Helm CLI lint/集群安装未在当前工作区验证，因此不构成生产 Go 证据。

## 2. 自动化测试覆盖

| 测试域 | 覆盖场景 |
|---|---|
| 配置安全 | 环境枚举、短密钥、生产开发认证 fail-fast、JWKS 必填边界 |
| JWT | 缺失、过期、错误 issuer/audience、无签名/错误签名、必要 claims |
| 身份 | `/me`、角色/permissions、未知与 disabled 用户、租户状态 |
| 租户隔离 | Repository 必填作用域、跨租户 ID 404、用户私有边界 |
| 会话 | create/get/list/patch/delete、字段校验、权限、审计 |
| 并发 | 10 个并发创建 ID 唯一；旧 ETag 更新返回 412 |
| 分页 | keyset 顺序、next cursor、篡改签名、跨作用域绑定 |
| OIDC | discovery/JWKS、Code + PKCE、错误 verifier、code 一次性/重放拒绝 |
| 日志 | request/trace 关联；token、Authorization、email 不泄露 |
| 契约 | canonical OpenAPI 3.1 可解析，S1 `/me` 等 schema 存在 |

执行结果：

```text
21 passed, 9 subtests passed
warnings: treated as errors
coverage: 89.66% (gate >= 85%)
```

测试入口：`tests/unit` 与 `tests/integration`；统一命令在 `scripts/check.ps1`。

## 3. 静态检查与构建

| 门禁 | 结果 | 说明 |
|---|---|---|
| Python compileall | PASS | API、脚本、Fake IdP、Worker、测试 |
| Ruff | PASS | API、Fake IdP 与测试 |
| Mypy | PASS | API 与 Fake IdP |
| Web ESLint | PASS | Next.js App Router/BFF |
| Web TypeScript | PASS | `tsc --noEmit` |
| Next.js production build | PASS | `/`、auth、health、qa proxy 路由生成成功 |
| OpenAPI parse | PASS | OpenAPI 3.1，canonical 路径总数 15（含未来阶段） |
| Compose config | PASS | 环境变量齐全时静态解析通过 |
| Helm lint | DEFERRED | 当前机器未安装 Helm CLI；Chart 已静态审查 |

## 4. 数据库验证

- SQLite：Alembic `upgrade head → downgrade base → upgrade head` 通过。
- PostgreSQL：Compose 中 migrate 容器退出码 0，API 依赖 migrate 完成后启动健康。
- 初始化缺陷：首次 PostgreSQL 全栈发现 ORM 可能先插入 role 后插入 tenant，触发外键失败；已将种子改为 tenant flush → user/role flush → user_role，随后重新构建并验证通过。
- 限制：S1 没有开启 RLS；生产采用 RLS 时必须新增连接池上下文设置/清理测试。

## 5. 容器与端到端证据

成功构建：`enterprise-qa-api`、`enterprise-qa-worker`、`enterprise-qa-fake-idp`、`enterprise-qa-web`。完整 Compose 启动状态：PostgreSQL、Redis、MinIO、Fake IdP、API 均 healthy；migration exited 0；Worker、Web、OTel Collector running。

`scripts/smoke_s1.py` 通过真实 HTTP 跟随登录重定向并验证：

1. Fake IdP Authorization Code + PKCE 登录并设置 BFF HttpOnly access token。
2. BFF `/api/qa/me` 返回 `tenant.code=demo_corp`。
3. 带双提交 CSRF 创建会话返回 201。
4. 响应包含 conversation ID 与 request ID。

冒烟后使用 `docker compose down` 停止并删除测试容器/网络，未删除命名数据卷。

## 6. 供应链验证

| 检查 | 结果 |
|---|---|
| `pip-audit -r requirements.lock` | PASS，0 known vulnerabilities |
| `npm audit --audit-level=moderate` | PASS，0 vulnerabilities |
| Python 运行依赖精确锁定 | PASS |
| `package-lock.json` + `npm ci` | PASS |
| Gitleaks workflow | 已配置，远端执行待 GitHub 仓库 |
| 镜像构建 workflow | 已配置，本地四镜像已构建 |

本机 BuildKit 在读取基础镜像 metadata 时出现 Docker/registry cache `failed size validation`；未删除用户缓存，改用 legacy builder 完成相同 Dockerfile 的本地验证。GitHub Actions 中的 BuildKit/标准 `docker build` 仍需首次远端 CI 证明。

## 7. 未验证项与证据效力

- 没有企业 OIDC 账号/配置，Fake IdP 结果不能证明 MFA、组映射、登出、JWKS 轮换和禁用 SLA。
- 当前目录没有 Git 仓库/远端环境，workflow 文件不能证明 main commit 已自动部署 dev。
- 没有 Helm CLI 和 Kubernetes 集群，未执行 lint、template、install、rollback、NetworkPolicy 或 Secret Manager 验证。
- 30 分钟新开发者目标已通过脚本化流程设计并在现有机器复演，但尚无独立新成员计时记录。
- S1 无模型与真实知识，因此 AI 质量、性能、成本门槛不适用，仍沿用 S0 作为后续发布门禁。

## 8. 复验命令

```powershell
.\scripts\check.ps1 -OnlineAudit
.\scripts\dev.ps1
# 新终端
.\.venv\Scripts\python.exe scripts\smoke_s1.py
.\scripts\dev.ps1 -Down
```

接入企业平台后追加：`helm lint`/`helm template`、dev namespace install、企业 OIDC 负向套件、main 自动部署记录、镜像 digest/SBOM/签名与回滚证据。

