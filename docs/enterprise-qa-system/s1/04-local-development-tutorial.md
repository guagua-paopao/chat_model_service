# S1 本地开发与教学手册

## 1. 前置条件

- Windows PowerShell 5.1+；Python 3.12；Node.js 22；Docker Desktop 26+。
- 建议预留 6 GB 内存与 10 GB 镜像空间。
- 仅使用合成数据。不要把企业 token、真实文档或正式密钥放入本环境。

检查：

```powershell
python --version
node --version
docker version
docker compose version
```

## 2. 首次安装（目标 30 分钟内）

在仓库根目录 `D:\codex\model`：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，将每个 `CHANGE_ME` 替换为不同的本地随机值。JWT 与 cursor key 至少 32 字符；`.env` 已被 gitignore，仍应在提交前检查。

```powershell
.\scripts\setup.ps1
.\scripts\check.ps1 -OnlineAudit
```

若企业 Windows 策略直接拦截 `.ps1`，可对单次子进程使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 -OnlineAudit
```

该写法不修改系统 ExecutionPolicy；若组织政策明确禁止 bypass，应联系终端管理员使用批准的签名脚本流程。

`setup.ps1` 创建 `.venv`、安装锁定 Python 依赖和 `npm ci`。`check.ps1` 执行 Ruff、Mypy、严格 pytest/覆盖率、迁移 up/down/up、OpenAPI 解析、Web lint/type/build、Compose config，以及在线 npm/pip audit；本机没有 Helm 时会明确跳过 lint。

## 3. 启动与端到端验证

```powershell
.\scripts\dev.ps1
```

等待 API 显示 healthy 后打开 `http://127.0.0.1:3000`，点击登录。Fake IdP 默认使用 `demo` persona；页面应显示 `demo_corp`，并能创建空会话。

另开终端运行自动冒烟：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_s1.py
```

预期：`S1 smoke passed`，并打印 tenant、conversation ID 与 request ID。

停止服务但保留命名数据卷：

```powershell
.\scripts\dev.ps1 -Down
```

若要清空合成数据，必须先确认没有需要保留的本地实验，再由开发者显式执行带 volume 删除的操作；脚本默认不删除数据卷。

## 4. 直连 API 练习

本地辅助令牌用于理解 API，不替代 OIDC 冒烟：

```powershell
$token = & .\.venv\Scripts\python.exe apps\api\scripts\issue_dev_token.py demo
$headers = @{ Authorization = "Bearer $token" }
$me = Invoke-RestMethod http://127.0.0.1:8000/api/v1/me -Headers $headers
$me
```

创建会话并保存 ETag：

```powershell
$body = @{ title='接口练习'; channel='api'; knowledge_base_ids=@(); metadata=@{lesson='s1'} } | ConvertTo-Json
$response = Invoke-WebRequest http://127.0.0.1:8000/api/v1/conversations -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$conversation = $response.Content | ConvertFrom-Json
$etag = $response.Headers.ETag
```

更新并制造一次冲突：

```powershell
$patch = @{ title='接口练习 v2' } | ConvertTo-Json
Invoke-WebRequest "http://127.0.0.1:8000/api/v1/conversations/$($conversation.id)" -Method Patch -Headers ($headers + @{'If-Match'=$etag}) -ContentType 'application/json' -Body $patch
# 再使用旧 $etag 请求一次，应得到 412 ETAG_MISMATCH。
```

## 5. 三项教学实验

### 实验 A：解码不等于验证

1. 将开发 token 的三个 `.` 分段做 Base64URL 解码，观察 header/claims。
2. 修改 payload 中 `tenant_id` 但不重新签名，请求 `/me`。
3. 预期 401。结论：能读取 JWT 不代表声明可信；只有完整算法限制、签名和 `iss/aud/time` 校验后才能建立 Principal。

对应测试：`tests/unit/test_config_and_security.py`、`tests/integration/test_api.py`。

### 实验 B：让漏租户查询在边界失败

1. 查看 `ConversationRepository.get/list/update/delete` 的 keyword-only 签名。
2. 在临时练习分支尝试只传 `conversation_id` 调用，Mypy/运行时应失败。
3. 使用 other tenant token 猜 demo conversation ID，预期与不存在资源相同的 404。
4. 不要保留任何绕过 Repository 的生产查询。

对应测试：`tests/unit/test_repository_contract.py`、`tests/integration/test_api.py`。

### 实验 C：Contract-first 增加字段

以可选 `client_label` 为练习（不要直接提交到主干）：

1. 先修改 `docs/enterprise-qa-system/openapi.yaml` 的请求/响应 schema 和示例。
2. 修改契约测试，先看到失败。
3. 再添加迁移/模型、Pydantic 字段、Repository、API 与 Web 展示。
4. 运行 `scripts/check.ps1`，确认旧客户端仍兼容；若字段语义影响安全，先写 ADR。

## 6. 常见故障

| 现象 | 检查 | 处理 |
|---|---|---|
| `.env` 缺失/CHANGE_ME | `Get-Content .env` | 从 example 复制并生成不同随机值，不提交 |
| API 一直 unready | `docker compose ... ps -a`、API/Postgres 日志 | 先看 migrate 是否 0、Postgres 是否 healthy |
| 登录循环/state 错误 | 浏览器 cookie、`QA_WEB_PUBLIC_URL`、redirect URI | 三者必须精确使用 `http://127.0.0.1:3000` |
| JWKS/issuer 失败 | `QA_OIDC_ISSUER` 尾部 `/`、内部 JWKS URL | issuer 必须与 token 完全一致；不要改成容器内部 issuer |
| 变更请求 403 | `qa_csrf` 与 `X-CSRF-Token` | 浏览器页面/BFF 应自动处理；自写客户端需双提交 |
| PATCH 428/412 | If-Match 是否存在/最新 | 重新 GET 获取 ETag 后合并修改 |
| Docker BuildKit metadata size validation | Docker Desktop/registry cache | S1 已用 legacy builder验证 Dockerfile；重启/升级 Docker 后在 CI 复验 BuildKit，勿删除用户镜像缓存 |
| Helm 检查跳过 | `helm version` | 安装批准版本后运行 `helm lint infra/helm/qa-system` |

## 7. 开发流程

需求/威胁 → ADR（如改变边界）→ OpenAPI/迁移 → 失败测试 → 实现 → 本地检查 → PR/CI → dev 冒烟 → 更新阶段证据。不得用手工演示替代负向测试，不得在 API 启动中执行生产迁移。
