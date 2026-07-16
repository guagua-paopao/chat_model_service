# S5 开发教学、测试计划与故障注入

## 1. 学习目标

完成本阶段后，开发者应能解释并亲手验证：认证与授权的区别；为何不能信任 token role/group；ACL 为什么必须在 top-k 前；配置不可变与职责分离；ETag 和状态机如何阻止竞态；配额窗口/租约/账本的不同职责；哈希链能检测什么、不能防什么；为何本地评测和本地 dashboard 不能等同生产证据。

## 2. 建议开发顺序

### Step 1：建立失败测试

先写以下负向用例：员工访问 `/admin/users` 得 403；disabled token 得 403；group-only ACL 之前无结果；creator 自批/未评测发布失败；一分钟第二请求 429；篡改 audit reason 后 integrity=false。保持测试失败，再实现功能。

### Step 2：扩展目录态

1. migration 增加 user version/sync/disabled，groups/group_members。
2. seed 独立 governance/approver/auditor persona，避免让 demo employee 变成超级用户。
3. IdentityRepository 只查询当前 tenant 的 active user、有效 role/group。
4. Principal 加 groups；`/me` 只用于展示，不把返回值作为后续授权输入。

教学检查：给 JWT 人工加 `groups=["secret-admins"]`，系统行为必须不变。

### Step 3：集中 Policy

把路由中的散落 `if permission` 替换为 `PolicyEngine.require`。Repository tenant 条件保留；Policy 是第一层决策，不替代数据层隔离。给不存在的权限写测试，必须 403。

### Step 4：接通 group ACL

在 ingestion debug、RAG secure candidate 和 citation reauthorization 三处加入 group subject。ACL fingerprint 加 sorted groups。创建只含 group ACL 的文档，用 demo employee 验证可见；移除 membership 后应不可见（生产还要缓存失效测试）。

### Step 5：配置状态机

1. Draft 校验 exact schema/bounds，计算 canonical checksum。
2. Evaluation 由服务器构造 dataset/evaluator 版本；保存 metrics/thresholds/failed checks。
3. Approval 检查 passing 且 approver != creator。
4. Publish 事务归档 current、发布 candidate、写 hash audit。
5. Rollback clone 历史版本，不修改旧行。

故障注入：把 `min_relevance` 改为 0.1，门禁应 failed；删掉 `{context_json}` 或引用条款应 failed；伪造客户端 `gate_result` 应因 extra field/无字段入口而失败。

### Step 6：共享配额

将 session factory 注入 QuotaManager。使用 tenant row lock 串行化准入；窗口和租约显式赋默认值，避免 ORM default 只在 INSERT 时生效导致 Python `None += 1`。在 finally 释放，TTL 兜底。

故障注入：限制 req/min=1；让第一次成功后第二次 429。手工插入未过期 lease 达到 tenant/user 上限；过期 lease 不应阻断。关闭 quota policy 返回 403 且 ModelInvocation 为 0。

### Step 7：治理哈希链

canonical payload 必须固定 key/时间/Unicode 表达。写入前锁 tenant，取 last sequence/hash；unique(tenant,sequence) 防重复。验证从 ZERO_HASH 顺序重算。

故障注入：修改 reason、删中间行、改 sequence 或 previous_hash，均应定位 first invalid sequence。注意测试直接改 DB 仅用于验证检测，实际响应必须先取证。

### Step 8：事件/摘要/UI

安全事件用明确状态表拒绝非法跳转；resolved/closed 要求 safe resolution。摘要限制 31 天且 tenant-scoped。BFF regex 只放行已知 admin resource；写操作继续要求 CSRF。完成 lint/type/build。

## 3. 自动测试矩阵

| 层级 | 测试 | 关键断言 |
|---|---|---|
| Unit | settings/security/policy | production 禁 local evaluator，token claim 不授权 |
| Unit | config validator | exact keys、type、bounds、Prompt boundary |
| Unit | hash canonicalization | Unicode/time 固定，任意字段变化 hash 变化 |
| Integration | identity lifecycle | ETag、自我停权、next-request disable |
| Integration | group ACL | group-only 文档可见、current membership 生效 |
| Integration | config | evaluate/independent approve/publish/rollback/invalid transitions |
| Integration | quota | minute/user/tenant/token/cost/expired lease/disabled policy |
| Integration | audit | sequence、safe details、query permission、tamper detect |
| Integration | incidents | owner tenant、状态迁移、resolution、ETag |
| Contract | runtime + canonical OpenAPI | S5 path/field/status/error |
| Migration | upgrade/downgrade/upgrade | 0005/0006 表/列/约束可重建 |
| Web | lint/type/build | `/admin` 和 BFF allowlist |
| Full-stack | Compose/PostgreSQL | migration、persona、config、quota、audit smoke |
| Security | gitleaks/pip/npm/image | 0 high/critical 未接受 |

## 4. 手工 API 演练

```powershell
$admin = & .\.venv\Scripts\python.exe apps\api\scripts\issue_dev_token.py governance
$headers = @{ Authorization = "Bearer $admin" }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/admin/users -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/admin/groups -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/admin/rag-configs -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/api/v1/admin/quota-policies/tenant -Headers $headers
```

写操作建议通过 Swagger 或 `scripts/smoke_s5.py`，避免 PowerShell JSON/ETag 转义掩盖契约问题。

## 5. 本地验证命令

```powershell
.\.venv\Scripts\python.exe -m ruff check apps/api/src apps/api/scripts apps/fake-idp/src scripts tests
.\.venv\Scripts\python.exe -m mypy --strict apps/api/src
.\.venv\Scripts\python.exe -m pytest -W error --cov=qa_api --cov=fake_idp --cov-fail-under=85
.\.venv\Scripts\python.exe scripts\evaluate_s4.py
.\.venv\Scripts\python.exe scripts\validate_contracts.py
```

Web：

```powershell
Push-Location apps\web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
Pop-Location
```

若本机已有 Next dev server 锁住 `.next/trace`，可设置临时 `NEXT_DIST_DIR=.next-s5`；仓库的 next config 支持该变量，CI 仍使用默认 `.next`。

## 6. 生产前追加验证

- 企业 IdP/SCIM：10k 用户/组批同步、增量、重放、乱序、停权 P95/P99。
- PostgreSQL：同 tenant quota 100/500 并发锁等待、死锁、主从切换、连接池耗尽。
- 配置：真实黄金集/holdout/红队，外部 Worker 签名报告、并发 publish、灰度与回滚。
- 审计：WORM/SIEM 丢包/重试/对账、权限分离、保留/删除/法务封存。
- 观测：告警触发、抑制、升级、on-call 响应；无正文/PII/secret 扫描。
- 部署：Kubernetes migration job、PDB/HPA、NetworkPolicy、secret manager、Ingress SSE、备份恢复达到 RPO/RTO。

## 7. 常见误区

- “JWT 已验签所以 role/group 可信”：签名只证明 IdP 发出，不证明映射适合当前应用或足够新鲜。
- “哈希链等于不可篡改”：攻击者若能重写全部行可重算；必须外部锚定/WORM。
- “Redis 一定比数据库更企业级”：正确性、故障语义和运维成熟度优先；先有强一致基线再 benchmark。
- “评测 API 返回 passed 就能上线”：S5 local gate 只做结构安全；真实业务质量、holdout、红队和签字缺一不可。
- “管理员能做所有事更方便”：创建/审批/发布职责分离是为了限制单账户错误和滥用。
