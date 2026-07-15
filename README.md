# 企业级大模型问答系统建设计划

完整项目文档位于 [docs/enterprise-qa-system/README.md](docs/enterprise-qa-system/README.md)。

当前项目状态和不可违反的约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。阶段证据包：

- [S0 发现与基线](docs/enterprise-qa-system/s0/README.md)
- [S1 工程骨架、认证与租户](docs/enterprise-qa-system/s1/README.md)
- [S2 Model Gateway 与流式聊天](docs/enterprise-qa-system/s2/README.md)

建议从以下三份开始：

1. [项目章程与范围](docs/enterprise-qa-system/00-project-charter-and-scope.md)
2. [16 周阶段计划与开发教学](docs/enterprise-qa-system/05-stage-plan-and-tutorials.md)
3. [GitHub 参考项目评估](docs/enterprise-qa-system/11-github-reference-projects.md)

可执行契约：

- [OpenAPI 3.1](docs/enterprise-qa-system/openapi.yaml)
- [PostgreSQL + pgvector 参考 DDL](docs/enterprise-qa-system/schema.sql)

## S2 本地启动

要求：Python 3.12、Node.js 22、Docker 26+。PowerShell 中执行：

```powershell
Copy-Item .env.example .env
# 编辑 .env，替换所有 CHANGE_ME；不要提交 .env。
.\scripts\setup.ps1
.\scripts\check.ps1 -OnlineAudit
.\scripts\dev.ps1
```

若本机策略禁止执行 `.ps1`，可对单次子进程使用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 -OnlineAudit`；这不会修改系统执行策略。

另开终端生成 30 分钟本地开发令牌并验证可信租户上下文：

```powershell
$token = & .\.venv\Scripts\python.exe apps\api\scripts\issue_dev_token.py demo
Invoke-RestMethod http://127.0.0.1:8000/api/v1/me -Headers @{Authorization="Bearer $token"}
```

浏览器端到端验证（需 Compose 已启动）：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_s2.py
```

开发令牌和 Fake Provider 只允许 `local/test/dev`，生产配置会在启动时拒绝它们。S2 只提供通用模型回答，不使用企业知识或引用。完整教学、字段和故障注入见 [S2 开发手册](docs/enterprise-qa-system/s2/04-development-tutorial-and-fault-injection.md)。
