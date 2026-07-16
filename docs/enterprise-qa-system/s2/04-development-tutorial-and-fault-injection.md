# S2 开发教学与故障注入

## 1. 学习目标

完成本教程后，开发者应能解释 Adapter 与 Gateway 的边界、SSE 为什么需要终态事件和心跳、为什么可见输出后不能切模型、如何验证取消释放资源，以及 estimated usage 对财务语义的影响。

## 2. 环境准备与启动

要求 Python 3.12、Node.js 22、Docker 26+。不要把真实 API key 写入 `.env` 或提交到 Git。

```powershell
Copy-Item .env.example .env
# 替换 CHANGE_ME，本地保持 QA_FAKE_MODEL_ENABLED=true、QA_MODEL_PROVIDER_ENABLED=false
.\scripts\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1
.\scripts\dev.ps1
```

浏览器打开 `http://127.0.0.1:3000`，使用本地 Fake OIDC 登录。页面会明确提示当前为通用模型回答，没有企业知识库和引用。

## 3. 直接验证 API

生成开发 token 并创建会话：

```powershell
$token = & .\.venv\Scripts\python.exe apps\api\scripts\issue_dev_token.py demo
$headers = @{Authorization="Bearer $token"}
$conversation = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/conversations `
  -Headers $headers -ContentType application/json `
  -Body '{"title":"S2 教学","channel":"api","knowledge_base_ids":[]}'
```

非流式回答：

```powershell
$body = @{
  conversation_id = $conversation.id
  message = "用三点说明 SSE 的作用"
  stream = $false
  response_mode = "general"
  model_policy = "balanced"
  knowledge_base_ids = @()
} | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/chat/completions `
  -Headers $headers -ContentType application/json -Body $body
```

PowerShell 的高层 REST 命令会缓冲响应。观察原始 SSE 建议使用：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/v1/chat/completions `
  -H "Authorization: Bearer $token" -H "Content-Type: application/json" `
  -d "{\"conversation_id\":\"$($conversation.id)\",\"message\":\"流式说明当前阶段\",\"stream\":true,\"response_mode\":\"general\"}"
```

检查事件顺序：started → 至少一个 delta → usage → completed；`id` 连续递增，响应长时间无事件时可见 `: keep-alive`。

## 4. Fake Provider 故障实验

Fake 指令只供 local/test/dev；其输出确定性，便于测试而不消耗模型费用。

| 问题中加入 | 行为 | 要观察的证据 |
|---|---|---|
| `[429]` | 主路由首次限流，备用成功 | 最终 model 为 backup；invocation 先 failed 后 completed |
| `[all-429]` | 所有路由限流 | 非流式 429 / 流式 error；消息 failed |
| `[timeout]` | Provider 超时 | `MODEL_TIMEOUT`、retryable=true、重试次数不超预算 |
| `[blocked]` | 内容策略阻断 | 不重试，稳定 `MODEL_CONTENT_BLOCKED` |
| `[interrupt]` | 已输出部分 delta 后中断 | 不切备用拼接，消息 failed |
| `[missing-usage]` | 成功但缺 usage | 账本存在且 `estimated=true` |
| `[slow]` | 放慢分片 | 可在 UI 点击停止并验证 cancelled |

教学任务 A：比较 `[429]` 和 `[interrupt]` 的 invocation 记录，解释“未输出前可 failover、输出后不可”的用户一致性理由。

教学任务 B：把 `QA_CHAT_REQUESTS_PER_MINUTE=1`，连续发两次请求，验证第二次 429 且不会创建多余消息；一分钟后恢复。

教学任务 C：发送超出 `QA_CHAT_MAX_INPUT_TOKENS` 的文本，确认在 Provider 调用前被拒绝，并说明预估 token 只能用于保护预算，不能替代真实计费 usage。

## 5. 新增 Adapter 的步骤

1. 实现 `ModelAdapter` 协议，仅负责 Provider 请求、流解析和错误映射。
2. 为 2xx 流、usage、429、5xx、超时、非法 JSON/SSE、内容阻断和取消编写 `MockTransport` 契约测试。
3. 在 `build_model_gateway` 中通过配置注册 route；不要把 endpoint 或 key 加入公开请求/响应。
4. 设置 route code、能力、政策、context 上限、并发和价格快照；价格必须经 FinOps/采购确认。
5. 完成供应商安全、区域、训练使用、保留期和 DPA 审批后，才可在非本地环境启用。
6. 使用合成、非敏感提示做 canary；真实知识数据要等 S3/S4 数据政策和路由控制完成。

## 6. 可选批准沙箱

仅在已有批准时设置：

```text
QA_FAKE_MODEL_ENABLED=false
QA_MODEL_PROVIDER_ENABLED=true
QA_MODEL_PROVIDER_BASE_URL=https://approved-gateway.example/v1
QA_MODEL_PROVIDER_MODEL=approved-model
QA_MODEL_PROVIDER_API_KEY=<从 Secret Manager 注入，不写入文件>
```

`staging/production` 会拒绝 Fake、HTTP URL、空 key 或空模型名。这是 fail-fast 配置保护，不代表端点本身已通过治理审批。

## 7. 数据库迁移演练

```powershell
$env:QA_DATABASE_URL = "sqlite+pysqlite:///./.local/migration-check.db"
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c alembic.ini downgrade base
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

正式环境只由独立 migration Job 执行，API 不自动改 schema。生产回滚优先采用前向修复；`downgrade` 仅用于开发验证，因为删除 S2 表/字段会丢失审计和账本数据。

## 8. 全栈冒烟与排障

```powershell
.\.venv\Scripts\python.exe scripts\smoke_s2.py
docker compose -f infra\compose\compose.yaml logs api web migrate
```

| 症状 | 检查 | 处理 |
|---|---|---|
| 401 | OIDC issuer/audience、Cookie、token 时钟 | 重新登录；不要放宽签名/issuer 校验 |
| 403 CSRF | `qa_csrf` Cookie 与 `X-CSRF-Token` | 由页面/BFF 正常发送，不禁用保护 |
| 409 knowledge unavailable | response_mode/KB IDs | S2 使用 general；知识能力等 S3/S4 |
| SSE 被缓冲 | 代理超时、buffering、响应头 | 保留 no-buffering、流式转发和 ≥15s idle timeout |
| 429 | 用户/租户/route 限额 | 根据 request_id 查调用；不要盲目扩大预算 |
| 重启后 streaming 悬挂 | 启动恢复日志、消息更新时间 | 恢复器会标记失败；生产需共享取消/租约机制 |
| 金额为估算 | `usage_ledger.estimated` | 不能作为供应商对账最终依据，需标记数据质量 |
