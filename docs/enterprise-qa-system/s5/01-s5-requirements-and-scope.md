# S5 需求、应用场景与范围

## 1. 阶段目标

S5 的目标不是增加更多“能回答的问题”，而是让身份、配置、资源和安全操作进入可验证的企业流程。完成标准是：未经授权不能操作；高风险变更必须有原因、版本、独立审批和回滚；配额在多个 API 实例间一致；治理事件可发现篡改；所有结论有测试和文档证据。

## 2. 应用场景

### UC-S5-01：员工离职/停权

IAM 管理员将用户从 active 改为 disabled，提交审批号和原因。已有 JWT 在下一次请求解析时被拒绝，组/角色不再参与 ACL；操作进入治理哈希链。自我停权被拒绝，陈旧 ETag 返回 412。

### UC-S5-02：组 ACL 知识访问

目录同步器维护 `all-employees` 等租户组。文档 ACL 指向 group code；检索在评分/top-k 前将当前服务端组集合加入授权条件，引用查看再次用当前组集合鉴权。JWT 自报的 group claim 不参与判定。

### UC-S5-03：RAG 配置变更

治理管理员创建 immutable draft，服务器运行带版本/checksum 的门禁，独立审批人审核 passing evidence，发布者发布并归档旧版本。任何阶段失败均不能跳转；创建人不能自批。

### UC-S5-04：质量回退

发布后出现质量告警，管理员选择已通过并曾发布的历史版本。系统不修改历史行，而是创建更高版本的 rollback clone，在同一事务归档当前配置并保存审批号、原因和目标 checksum。

### UC-S5-05：成本/滥用控制

管理员使用 ETag 更新 tenant 配额。每次聊天在 tenant 事务锁下检查分钟请求、tenant/user 活动租约、日 token 和月成本；失败时不调用模型，租约 TTL 处理进程崩溃。

### UC-S5-06：事件处置与审计

安全人员登记 P0～P3 事件，只存 trace/工单等安全证据引用。状态按有限状态机流转；审计员可读取安全事件、用量/质量摘要并验证 hash chain，不能修改配置、用户或事件。

## 3. 需求与验收

| ID | 优先级 | 需求 | 验收证据 |
|---|---:|---|---|
| IAM-008 | Must | 用户、角色、组均由 tenant-scoped 服务端目录态解析 | Principal/Repository 测试，JWT 不含授权字段 |
| IAM-009 | Must | disabled 在下一请求生效，自我停权和跨租户修改拒绝 | API 集成测试 |
| IAM-010 | Must | group ACL 在检索前和引用查看时生效 | group-only ACL 集成测试 |
| POL-001 | Must | 权限检查集中、未知权限 fail closed | `PolicyEngine` 单元/路由负向测试 |
| CFG-001 | Must | 配置 immutable、checksum、version、reason | 数据库约束/API 测试 |
| CFG-002 | Must | 服务器选择 evaluator/dataset，客户端不能自报 passing | evaluation API/字段检查 |
| CFG-003 | Must | 创建人与审批人职责分离，未评测/失败/未审批不能发布 | 状态机测试 |
| CFG-004 | Must | rollback 创建新版本，不重写历史 | rollback 测试与审计 |
| QUA-001 | Must | 跨实例共享分钟/并发/日 token/月成本准入 | DB 事务设计、速率测试、PostgreSQL 待压测 |
| QUA-002 | Must | 配额变更使用 ETag、原因、审批和治理审计 | API 测试 |
| AUD-001 | Must | 高风险治理日志按租户顺序哈希，可检测修改 | 篡改测试 |
| AUD-002 | Must | 日志/响应不含 Token、Secret、raw Prompt/正文 | 日志测试、审计白名单评审 |
| INC-001 | Must | P0～P3 事件有限状态机、Owner、证据和处置摘要 | API 状态迁移测试 |
| OBS-001 | Should | 最长 31 天低基数用量/质量摘要 | API/控制台 |
| UI-001 | Should | 治理控制台展示身份、配置、配额、质量、事件、审计完整性 | Next.js lint/type/build |
| SEC-001 | Must | P0/P1 未缓解时 Gate 为 No-Go | S5 Gate/风险登记 |
| DEP-001 | Must | 0005～0006 migrations 可升级/降级/再升级 | Alembic round-trip |

## 4. 范围

### 已纳入

- local/test 合成身份 persona；用户/角色/组表和组 ACL。
- 集中 RBAC/tenant/owner policy 基线。
- RAG 配置 draft/evaluate/approve/publish/rollback。
- tenant 配额管理与 DB 共享准入租约。
- 高风险治理哈希链、审计查询/验证。
- 安全事件台账、用量/质量摘要、只读治理控制台。
- OpenAPI、Alembic、Compose/Helm 开关、测试、ADR、Gate。

### 明确不在 S5 已完成范围

- 企业 IdP/SCIM、批量同步、乱序/重放和真实组源 SLA。
- 真实业务黄金集、claim-level LLM judge、holdout 和生产评测 Worker。
- WORM/SIEM、数据留存法务封存、真实审计员/数据 Owner 签字。
- Redis 跨实例取消、任务队列取消传播；数据库配额的极限性能优化。
- Prometheus/Grafana/Alertmanager/on-call 的目标环境接入。
- 真实 secret manager、KMS、NetworkPolicy、WAF、解析沙箱、SBOM 签名平台。
- Kubernetes dev/staging、负载/故障/备份恢复演练和生产上线。

## 5. 非功能门槛

- 安全：跨租户/越权成功数 0；raw secret/正文日志发现数 0；P0/P1 未缓解数 0 才可生产。
- 一致性：同 tenant config 只有一个 published；配额准入在 tenant 锁下串行化；治理 sequence 无空洞。
- 可用性：本地测试不等同 99.9% 证据；生产 SLO 仍按总文档要求。
- 性能：管理列表当前适合教学/小规模；真实目录必须补分页、索引基准和容量测试。
- 隐私：摘要最长 31 天且 tenant-scoped；禁止高基数 user/query/document 指标标签。

## 6. 退出条件判定

S5 本地候选完成需全部代码/迁移/契约/测试/文档通过。生产退出条件还要求企业 IAM、真实评测、WORM/SIEM、红队、Kubernetes、性能、DR 和正式签字；本交付不具备这些证据，因此 Gate 只能“条件通过后续合成开发，生产 No-Go”。
