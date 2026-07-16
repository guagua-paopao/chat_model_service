# S2 测试与验证报告

> 执行日期：2026-07-15  
> 环境：Windows + Python 3.12.3 + Node.js 22 + Docker Engine 26.1.1  
> 结论：合成开发门禁通过；生产/真实模型证据不完整

## 1. 自动化结果

| 检查 | 结果 | 证据摘要 |
|---|---|---|
| Ruff | 通过 | API、Fake IdP、脚本和测试无告警 |
| Mypy strict | 通过 | 15 个 source files 无问题 |
| Pytest | 通过 | 35 tests + 13 subtests |
| 覆盖率 | 通过 | 89.76%，门槛 85% |
| Model Gateway 单测 | 通过 | Fake fallback、缺 usage、partial 后禁 failover、OpenAI-compatible MockTransport、429 归一化 |
| Chat 集成 | 通过 | 同步/SSE、调用记录、账本、全部限流、知识模式拒绝、取消、重试、速率配额 |
| 契约 | 通过 | 运行时和 canonical OpenAPI 均包含 S2 paths；YAML 为 OpenAPI 3.1 |
| SQLite migration | 通过 | `upgrade head → downgrade base → upgrade head` |
| Next.js | 通过 | ESLint、TypeScript、生产构建 |
| Compose config | 通过 | 环境插值和服务依赖合法 |
| Helm lint | 未执行 | 本机未安装 Helm；保留为部署门禁 |

覆盖率明细：`chat.py 89%`、`model_gateway.py 91%`、`main.py 87%`、总计 `1699 statements / 174 missed = 89.76%`。

## 2. 全栈验证

使用隔离 Compose project 和全新卷完成：

1. 构建 API、Fake IdP、Worker、Web 四个应用镜像。
2. PostgreSQL、Redis、MinIO、Fake IdP、API 健康；migration Job 成功退出。
3. PostgreSQL `alembic_version = 20260715_0002`。
4. `scripts/smoke_s2.py` 完成 Fake OIDC Authorization Code + PKCE 登录、BFF `/models`、创建会话、SSE 提问、会话回读。
5. smoke 收到 10 个业务事件，包含 started、delta、usage、completed。
6. 数据库存在 1 条 model invocation、1 条 usage ledger，用户与助手消息均已完成。

首次复用旧本地卷时因旧数据库密码失败；验证过程保留原卷，改用新 project/新卷，证明迁移在干净 PostgreSQL 上可运行。首次并行容器构建在远端连接中断后出现下载 payload 与索引元数据哈希不一致，构建被 pip 阻断；没有关闭校验，改为串行重新下载后四个镜像全部成功。这两项均属于验证环境状态，不是通过修改产品代码掩盖。

## 3. 供应链审计

| 审计 | 结果 |
|---|---|
| `pip-audit -r requirements.lock` | 0 个已知漏洞 |
| `npm audit --audit-level=moderate` | 0 个已知漏洞 |
| 锁文件 | Python 精确版本 + npm lock 均已更新/保留 |
| Secret | 真实 Provider key 未进入测试、日志或 Git；Helm 仅引用 Secret key 名 |

“无已知漏洞”只代表执行时漏洞数据库结果，不代表代码或依赖绝对安全；CI 应持续重复审计并生成 SBOM/签名镜像。

## 4. 已验证的失败路径

- 主路由 429 后备用成功，调用尝试顺序和错误码入库。
- 所有 route 429 返回 `MODEL_RATE_LIMITED`，消息为 failed。
- 已产生 delta 后 Provider 中断不切备用，避免混合答案。
- 上游缺 usage 时估算并明确标记。
- 知识模式/KB ID 在 S2 被 409 拒绝。
- 重复取消幂等；跨租户目标不可枚举；failed 消息可重试且不重复用户消息。
- 非规范 Base64URL 签名游标被拒绝，修复了 S1 遗留的等价编码篡改边界。

## 5. 尚未形成的证据

- 没有真实批准 Provider 的网络、协议、效果、账单、区域或数据治理验证。
- 没有目标环境 TTFT/总耗时 P95、并发、长连接、断线风暴和熔断恢复压测。
- 主动取消与客户端断线已实现并有状态/作用域测试，但尚无多副本共享协调和故障注入压测。
- 没有 Helm lint、Kubernetes 安装、Ingress SSE idle timeout、Secret Manager、NetworkPolicy 和滚动发布验证。
- 没有正式 Prometheus dashboard/alert、供应商账单对账或生产保留策略。

因此本报告只能支持 S3 合成开发，不能支持真实数据、staging 多副本或生产发布。
