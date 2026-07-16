# 企业级大模型问答系统建设计划

完整项目文档位于 [docs/enterprise-qa-system/README.md](docs/enterprise-qa-system/README.md)。

当前项目状态和不可违反的约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。阶段证据包：

- [S0 发现与基线](docs/enterprise-qa-system/s0/README.md)
- [S1 工程骨架、认证与租户](docs/enterprise-qa-system/s1/README.md)
- [S2 Model Gateway 与流式聊天](docs/enterprise-qa-system/s2/README.md)
- [S3 安全文档摄取与调试检索](docs/enterprise-qa-system/s3/README.md)
- [S4 可溯源 RAG 闭环](docs/enterprise-qa-system/s4/README.md)
- [S5 企业治理闭环](docs/enterprise-qa-system/s5/README.md)
- [S6 质量、可观测性、韧性与恢复](docs/enterprise-qa-system/s6/README.md)
- [S7 UAT、灰度发布与运营移交](docs/enterprise-qa-system/s7/README.md)

建议从以下三份开始：

1. [项目章程与范围](docs/enterprise-qa-system/00-project-charter-and-scope.md)
2. [16 周阶段计划与开发教学](docs/enterprise-qa-system/05-stage-plan-and-tutorials.md)
3. [GitHub 参考项目评估](docs/enterprise-qa-system/11-github-reference-projects.md)

可执行契约：

- [OpenAPI 3.1](docs/enterprise-qa-system/openapi.yaml)
- [PostgreSQL + pgvector 参考 DDL](docs/enterprise-qa-system/schema.sql)

## S7 本地启动

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

浏览器端到端验证与确定性评测（需 Compose 已启动）：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_s4.py
.\.venv\Scripts\python.exe scripts\evaluate_s4.py
.\.venv\Scripts\python.exe scripts\smoke_s5.py
.\.venv\Scripts\python.exe scripts\smoke_s6.py
.\.venv\Scripts\python.exe scripts\fault_s6.py
.\.venv\Scripts\python.exe scripts\drill_s6_recovery.py
.\.venv\Scripts\python.exe scripts\load_s6.py --profile smoke --duration 3 --rps 2
.\.venv\Scripts\python.exe scripts\smoke_s7.py
```

开发令牌、Fake Provider/Embedding/Reranker 和签名扫描器只允许 `local/test/dev`，生产配置会在启动时拒绝它们。S4 提供 ACL-first hybrid retrieval、grounded/search-only、引用再鉴权与拒答，但合成评测不代表真实业务质量。完整教学、字段和故障注入见 [S4 开发手册](docs/enterprise-qa-system/s4/04-development-tutorial-and-fault-injection.md)。

## S7 当前基线

S7 已在本地/合成范围完成不可变发布候选、UC-01～05 UAT、五类独立签署、dark→5%→25%→50%→100% 灰度、自动停止/回滚、事件哈希链和运营移交文档。阶段证据包见 [S7 README](docs/enterprise-qa-system/s7/README.md)。

只允许使用合成、公开或明确批准的非敏感资料。生产仍要求关闭全部 S6 阻断项，并接入企业 IAM/CAB、真实 registry/SBOM/签名、生产同构 staging、外部 Rollout Controller、可信指标、目标压测与 DR。S7 local release rehearsal PASS 不是生产批准。
