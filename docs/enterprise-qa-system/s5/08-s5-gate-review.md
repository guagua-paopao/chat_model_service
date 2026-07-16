# S5 Gate 评审

> 评审日期：2026-07-16  
> 决策：**本地工程候选通过；仅条件允许后续合成/逐项批准的 S6 工作；真实数据、staging 与生产 No-Go。**

## 1. 评审边界

本 Gate 区分三种权限：

1. 本地工程完成：代码、契约、迁移、测试和文档是否形成闭环。
2. 进入 S6：是否可继续使用合成、公开或逐项批准的非敏感数据做质量、性能、可观测和恢复工程。
3. 生产发布：是否已具备企业身份、安全、审计、质量、运维和责任人签字证据。

前两者不能推导第三者。

## 2. 条件检查

| 退出条件 | 结论 | 证据/缺口 |
|---|---|---|
| tenant/user/role/group 服务端授权 | 本地通过 | 集成测试；真实 IAM/SCIM 缺失 |
| RBAC + ACL 负向矩阵 | 本地通过 | 普通用户 403、group-only ACL、disabled next request |
| 配置评测、独立审批、发布和不可变回滚 | 本地通过 | passing/failed/SOD/rollback 集成与 smoke |
| 跨 API 实例共享配额状态 | 基线通过 | DB 窗口/lease；目标并发、failover 未测 |
| 审计可发现篡改 | 本地通过 | tenant hash chain + tamper test |
| 审计不可抵赖/独立保留 | 未通过 | 无 SIEM/WORM 外部锚定 |
| OWASP GenAI P0/P1 控制及红队 | 部分通过 | S3/S4 注入/越权回归；目标红队和签字缺失 |
| 日志/Trace/错误无 secret/正文 | 设计与测试通过 | 生产日志平台和持续扫描缺失 |
| 供应链与部署门禁 | 部分通过 | 依赖审计 0；无 SBOM、签名、K8s/Helm 实装 |
| 审计、数据、安全负责人签字 | 未通过 | 尚无具名 Owner/Approver 记录 |

## 3. 决策

### GO：允许的事项

- 在 `agent/s5-enterprise-governance` 本地分支继续维护 S5。
- 使用合成、公开或明确批准的非敏感数据进入 S6 工程。
- 接入真实企业组件前先做隔离 PoC、契约测试和数据分类审批。
- 逐项关闭风险登记，每个关闭动作附可复验报告和具名批准。

### NO-GO：禁止的事项

- 不得把 local evaluator 的 passing 宣称为业务质量或生产批准。
- 不得把数据库 hash chain 宣称为 WORM、不可抵赖或法务保全。
- 不得使用真实企业账号、真实知识、PII、密钥或生产 Provider，除非获得对应 Owner 书面批准并完成控制验证。
- 不得部署 staging/production、创建生产密钥、打开公网入口或承诺 SLO。
- 不得因本地依赖审计为 0 而跳过 SBOM、镜像签名、制品扫描和许可证审查。

## 4. 阻断生产的最小关闭清单

1. 企业 IAM：OIDC/SCIM、组映射、禁用/离职 SLA、重放/乱序、break-glass 和访问复核通过。
2. 质量与安全：批准的多语言业务集、独立 evaluator、holdout、Prompt injection/data poisoning/over-authorization 红队无未缓解 P0/P1。
3. 审计：治理事件可靠外送 SIEM/WORM，对账、留存、法律封存和独立权限验证通过。
4. 资源治理：tenant/user/service account/upload 配额、跨实例取消、目标负载锁竞争与故障语义通过。
5. 平台：Kubernetes、secret manager、TLS、NetworkPolicy、签名镜像/SBOM、备份恢复与 RPO/RTO 演练通过。
6. 运营：真实 dashboard/alert/on-call/Runbook 演练通过，产品、安全、数据、审计和 SRE 具名签字。

## 5. S6 入口约束

S6 可以设计质量、延迟、可靠性、成本仪表盘和压测/故障/恢复工具，但默认继续使用 Fake Provider 与非敏感数据。任何真实 Provider、企业 IdP、真实数据、外部消息或云资源接入都必须单独获得授权；S6 完成也不会自动授权 S7 或生产发布。
