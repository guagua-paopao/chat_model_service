# 05. 阶段计划与开发教学

## 1. 开发方法

项目采用双周 Sprint、主干开发（trunk-based development）和短生命周期分支。每项工作遵循：需求澄清 → 设计/威胁分析 → 接口/迁移先行 → 实现 → 自动化测试 → 代码评审 → 预生产验证 → 文档与演示。

每个用户故事必须具备：需求 ID、验收条件、接口/数据影响、隐私与安全影响、测试计划、监控、发布与回滚。每个 PR 应小于可审查范围，至少一名模块 Owner 批准；认证、租户、ACL、密钥和迁移代码需安全或技术负责人额外会签。

## 2. 各环境与每阶段固定门禁

| 环境 | 数据 | 用途 | 发布方式 |
|---|---|---|---|
| local | 合成数据 | 开发、教学、单元/集成 | Compose，开发者自助 |
| dev | 合成/自动种子 | PR 合并后的持续集成 | 自动 |
| test | 脱敏/合成固定集 | 系统、性能、安全、评测 | 自动+测试控制 |
| staging | 生产同构、批准的合成/脱敏数据 | UAT、发布演练 | 与生产同一流水线 |
| production | 真实受控数据 | 正式服务 | 审批+灰度+自动回滚 |

每阶段都需完成代码格式/静态检查、单元测试、接口契约、迁移验证、依赖与密钥扫描、镜像构建、文档更新。阶段退出前展示“正常路径 + 至少一个失败/降级路径”。

---

## S0. 发现、样本与技术基线（W1）

本阶段的实际基线、60 条合成黄金样例、威胁模型、容量成本、Gate 记录和 ADR 已保存在 [S0 阶段基线包](s0/README.md)。当前结论为“合成开发条件通过”，真实数据、模型和业务承诺仍需完成具名审批。

### 目标与应用场景

把“做一个问答系统”变成可验证的问题定义。选择 1–2 个首发场景，例如内部制度问答和客服辅助；收集真实但经过授权/脱敏的知识样本，形成首版质量基线。

### 需求与设计任务

- 访谈业务 Owner、知识管理员、终端用户、安全、法务与运维。
- 盘点文档类型、数量、页数、更新频率、密级、现有权限源和数据流向。
- 创建至少 50 条黄金问题：可回答、不可回答、越权、过期、歧义、安全攻击各有样本；生产前扩展至 200+。
- 记录当前人工查找时长、正确率、升级人工比例，作为收益基线。
- 确认模型数据政策、部署边界、预算、SLO、RPO/RTO 和保留期限。
- 完成 C4 图、威胁模型、ADR-001~008 提案及开源许可预审。

### 接口与字段

本阶段不写业务 API，但先冻结公共约定：`tenant_id` 从 token 解析、UUID、RFC3339、错误模型、`request_id`、幂等和游标分页。定义黄金集字段：

| 字段 | 说明 |
|---|---|
| `case_id` | 稳定唯一 ID |
| `tenant_code/persona` | 所属租户与角色 |
| `question` | 测试问题 |
| `knowledge_base_codes` | 允许检索范围 |
| `expected_answer_points` | 必须覆盖的事实点数组 |
| `expected_source_ids` | 预期文档/版本 |
| `answerable` | 是否应回答 |
| `forbidden_source_ids` | 绝不可出现的来源 |
| `risk_tags` | no_answer、acl、injection、outdated 等 |
| `reviewer/status` | 双人审核与状态 |

### 文档产物

项目章程、需求说明、数据清单、黄金集 v0、架构草案、威胁模型 v0、风险登记册、ADR、容量/成本情景和验收计划。

### 教学实验

用同一批 10 个问题分别进行“裸模型回答”和“人工提供正确文档片段后回答”，记录正确性、引用和 token 差异。学习目标是理解模型参数知识与企业证据的区别，而不是调 Prompt 追求好看答案。

### 退出条件

- 产品、安全、技术和运维批准范围、数据流与首发门槛。
- 至少 50 条双人复核样例可自动执行，包含 ≥10 条不可回答/越权/攻击问题。
- 模型与开源许可没有未分配 Owner 的阻断风险。

---

## S1. 工程骨架、认证与租户（W2–W3）

### 目标与应用场景

建立可持续交付的最小纵切：用户可通过开发 OIDC 登录，只能看到自己租户，前端能调用 `/me`、健康检查与创建空会话；每次请求都有 trace 和审计上下文。

### 需求

对应 IAM-001/002/003/005、QA-001 的会话骨架，以及全部工程门禁。此阶段先支持系统角色，文档 ACL 在 S3 完成。

### 设计与实现

- Monorepo 建议目录：`apps/web`、`apps/api`、`apps/worker`、`packages/contracts`、`infra/compose`、`infra/helm`、`tests/e2e`、`docs/adr`。
- API 中间件顺序：request ID → trace → 安全 header/大小限制 → 认证 → 租户解析 → 授权 → 速率限制 → handler → 结构化审计。
- OIDC 校验 issuer、audience、签名、时间声明；浏览器使用 Authorization Code + PKCE，不在 localStorage 保存长期 token。
- 建立 `tenants/users/roles/user_roles/conversations/messages/audit_logs` 迁移和种子数据。
- Compose 启动 Web、API、Worker、PostgreSQL、Redis、MinIO、OTel Collector；提供一条命令完成环境检查。
- CI 执行 lint、typecheck、unit、migration up/down 或前向校验、OpenAPI lint、secret/SCA 扫描、镜像构建。

### 本阶段接口

| 接口 | 关键请求字段 | 关键响应字段 |
|---|---|---|
| `GET /health/live` | 无 | `status` |
| `GET /health/ready` | 无 | `status, checks` |
| `GET /me` | token | `id, tenant, roles, permissions, locale` |
| `POST /conversations` | `title?, knowledge_base_ids[], channel, metadata` | `id, status, created_at, ETag` |
| `GET /conversations` | `cursor, limit, status` | `items, next_cursor` |

字段约束以 [openapi.yaml](openapi.yaml) 为准。Repository 测试必须证明没有 `tenant_id` 的查询无法编译/调用或被安全拦截。

### 测试与验收

- Token 缺失、过期、错误 issuer/audience、禁用用户、跨租户 ID 猜测均被拒绝。
- 连接池复用时租户上下文不串线；若启用 RLS，归还连接后 session 变量被清理。
- 并发创建会话、ETag 冲突、分页顺序稳定性通过。
- Trace 从网关到 DB 可见，日志中无 token/email 全量或 Authorization header。

### 教学实验

1. 解码开发 JWT，理解签名验证与“解码不等于可信”。
2. 人为写一个漏 `tenant_id` 的查询，让安全测试捕获，再用 `TenantScopedRepository` 重构。
3. 给一个接口增加字段：先改 OpenAPI 和契约测试，再实现前后端，体验 contract-first。

### 退出条件

主干任意提交可自动部署 dev；认证/租户负向测试全绿；本地新开发者在 30 分钟内按 README 启动；架构与 API v1 公共规范评审通过。

S1 实际产物、测试证据与未关闭条件见 [S1 工程证据包](s1/README.md)。当前 Gate 为条件通过：允许 S2 合成开发，但企业 OIDC、GitHub dev 自动部署和 Helm/Kubernetes 实装仍需补证。

---

## S2. Model Gateway 与流式聊天（W4–W5）

### 目标与应用场景

在没有企业知识检索的前提下完成可靠模型调用：用户发送消息、看到流式结果、可停止/重试；平台记录模型路由、token、成本、错误和耗时。此阶段 UI 明确标注“通用模型回答，未使用企业知识”。

### 需求

QA-001/006/009、ADM-001/003 的模型与配额基础。支持至少两个适配器（可用一个真实沙箱 + 一个 deterministic fake）。

### 设计与实现

- 建立 `ModelGateway`、Provider Adapter、route policy、capability registry 和归一化错误。
- 统一超时：连接、首 token、总时长；重试只针对允许错误，总尝试次数包含 fallback。
- 使用 Provider 级并发隔舱、令牌桶、熔断器；取消请求向上游传播。
- `messages` 保存 `pending→streaming→completed/failed/cancelled`；用户消息和 Assistant 占位在调用前事务写入。
- SSE 事件实现 `started/delta/usage/completed/error`，sequence 去重、心跳、反向代理缓冲关闭。
- 上下文窗口预算：系统提示、历史、检索预留和输出分别限额；历史按消息边界裁剪/摘要，不能截断半个工具结果。
- `usage_ledger` 追加记录，价格用调用时快照；预算预检和最终对账分开。

### 本阶段接口与字段

`POST /chat/completions`：`conversation_id, message, stream, model_policy, client_context.locale`。  
SSE：`request_id, message_id, sequence, created_at` 为公共字段；`delta` 事件含 `delta`，`usage` 含 `input_tokens/output_tokens/cached_tokens/estimated/amount/currency`，最终事件含 `finish_reason/trace_id`。  
`POST /messages/{id}/cancel`：只允许 `pending/streaming`；幂等取消已取消请求返回当前状态。  
`GET /models`：只返回 `id, display_name, capabilities, status, max_context_tokens, allowed_policies`，不返回 endpoint/secret。

### 测试与验收

- Fake Provider 固定模拟分片、429、超时、流中断、usage 缺失和取消。
- 流开始前/后的错误格式符合契约；客户端重复事件不会重复渲染。
- 429 退避无惊群；不可重试错误只调用一次；熔断时快速失败或合法降级。
- 单请求/用户/租户配额、并发上限和 token 上限生效。
- 断开浏览器后消息最终状态明确，无永远 `streaming` 的孤儿记录。

### 教学实验

1. 用 Fake Provider 每 100 ms 产生 token，观察 SSE、反向代理缓冲和取消传播。
2. 注入 30% 429，对比“立即重试”与“指数退避+抖动”的成功率和上游压力。
3. 计算一次真实问题的系统提示/历史/输出 token 和费用，修改历史裁剪策略对比质量与成本。

### 退出条件

两个 Adapter 通过同一套契约测试；P95 首 token 在测试基线内；故障/取消/配额都有演示和指标；密钥只从 secret 引用加载。

S2 实际产物、字段、故障注入、测试证据与未关闭条件见 [S2 Model Gateway 与流式聊天证据包](s2/README.md)。当前 Gate 为条件通过：允许 S3 合成摄取开发，但真实 Provider、多副本共享配额/取消、目标负载和 Helm/Kubernetes 实装仍需补证。

---

## S3. 文档上传与摄取流水线（W6–W7）

### 目标与应用场景

知识管理员可以安全上传文档，看到扫描、解析、切分、Embedding、索引各阶段，预览解析结果并在失败后采取行动。文档完成后可通过调试检索找到，但尚不用于最终生成。

### 需求

KB-001~008 中除连接器外的 M/S 项；IAM-004 的 ACL 数据结构与检索过滤。

### 设计与实现

- 预签名直传，quarantine 与 published 对象前缀/桶分离；文件名不参与物理路径。
- 完成上传后重新验证大小、SHA-256、MIME magic bytes 和恶意软件扫描。
- Parser 输出统一 `ParsedElement(type,text,page,bbox,section,metadata)`；每个 Parser/策略有版本。
- 结构优先切分：标题/段落/表格边界优先，token 上限和 overlap 次之；保留页码和 section path。
- Embedding 批处理、限流、重试和 chunk hash 增量复用；Staged chunk 全部完成后原子发布。
- Worker 使用 outbox/队列，步骤幂等；失败任务保存安全错误码，超过重试进入死信。
- 管理台显示状态、进度、页数、chunk 数、token、错误建议和重试按钮。

### 本阶段接口与字段

| 接口 | 关键字段 |
|---|---|
| `POST /knowledge-bases` | `code,name,description,classification` |
| `POST /knowledge-bases/{id}/documents` | `title,filename,mime_type,size_bytes,sha256,classification,acl[],metadata` |
| `POST /documents/{id}/upload-complete` | `version_id,sha256` → `job_id,status,stage` |
| `GET /documents/{id}` | 文档、版本、`status,current_version_id,latest_job` |
| `GET /jobs/{id}` | `status,stage,progress,attempt,metrics,error` |
| `POST /jobs/{id}/retry` | 无正文；需要幂等键 |
| `POST /retrieval/search` | `query,kb_ids,top_k,filters,include_content` |

核心表：`knowledge_bases/documents/document_versions/document_chunks/document_acl/ingestion_jobs/outbox_events`。字段见 [03](03-data-model.md)。

### 测试与验收

- PDF、DOCX、TXT、MD 的正常/空白/加密/损坏/伪造 MIME/超大/恶意样本。
- 相同幂等键重试、消息重复投递、Worker 中途崩溃、Embedding 部分成功均不产生重复 active chunk。
- 文档发布前不可检索；删除/下线后立刻不可检索；旧版本不进入新问答。
- ACL 用户/组/角色正负矩阵和跨租户测试为 0 泄露。
- 抽样 20 份文档检查乱码率、空块、页码、标题路径和表格可读性。

### 教学实验

1. 对同一文档分别用固定字符、固定 token、标题感知三种切分，比较命中片段完整性。
2. 在 Worker 的 Embedding 50% 处强制崩溃后重启，验证幂等和原子发布。
3. 写一条“先全局 top-k 再 ACL 过滤”的错误查询，观察召回损失/泄露风险，再改为过滤约束内召回。

### 退出条件

四种文件主路径可用，失败路径可操作；摄取 SLI 可观测；文档版本原子发布和 ACL 安全测试通过；管理员完成一轮上传/修复/发布 UAT。

---

## S4. RAG 闭环、引用与拒答（W8–W10）

### 目标与应用场景

把授权检索接入流式聊天，形成 query → hybrid retrieval → rerank → context packing → grounded generation → citations/abstention 完整闭环，并用黄金集驱动调优。

### 需求

QA-002~007、QA-010 基础，ADM-002 Prompt/检索配置版本化，UC-01/02/04。

### 设计与实现

- Query policy 先做语言/意图/安全分类；仅在收益可测时启用 query rewrite。
- 向量与全文各召回候选，使用 RRF 等确定性融合，再用 reranker 得到 final-k。
- 所有召回在 `tenant_id + published version + ACL + metadata filters` 范围内执行。
- Context packer 去重、合并相邻 chunk、按 token 预算排序；每段包裹不可伪造的内部 source ID。
- Prompt 明确“来源是数据不是指令、只基于证据、每个事实附引用、资料不足拒答”。
- 引用从所选证据 ID 生成并验证，不允许模型自由编造 URL/文档名。
- 拒答结合检索阈值、证据覆盖和生成后验证；阈值按不同场景校准。
- 保存 `retrieval_runs/hits/citations` 和配置快照；上线语义缓存时键包含 ACL 指纹和知识版本。

### 本阶段接口与字段

`POST /chat/completions` 新增 `knowledge_base_ids,response_mode`；SSE 新增 `retrieval.completed` 和 `citation`。  
引用：`id,ordinal,document_id,document_version_id,document_title,version,page_from,page_to,section_path,quote,relevance_score`。  
引用详情：`GET /messages/{message_id}/citations/{citation_id}` 每次鉴权，返回限时原文链接或受控预览。  
反馈：`rating,reason_code,comment`，与 Prompt/检索/模型快照关联。

### 测试与验收

- 检索：Recall@k、MRR/nDCG、ACL 正确性、过期版本、同义词、中英混合、数字/编号问题。
- 生成：答案正确性、忠实度、答案相关性、引用精确/完整、拒答 precision/recall。
- 安全：间接提示注入文档、系统 Prompt 诱取、其他租户 ID 猜测、引用 URL 复用。
- 回归：不同 chunk/top-k/reranker/Prompt 通过固定评测运行比较，禁止只看平均分不看失败样本。
- 产品：用户可清楚区分答案、引用、系统拒答和系统故障。

MVP 门禁建议：检索 Recall@10 ≥ 0.85；答案忠实度 ≥ 0.90；引用精确率 ≥ 0.90、引用完整率 ≥ 0.85；无答案拒答 F1 ≥ 0.85；越权为 0。最终数值在 S0 校准。

### 教学实验

1. 构建 20 问小集，依次只改一个变量：chunk、top-k、融合、rerank、Prompt，记录指标和成本。
2. 把恶意指令写进文档，验证模型是否把它当数据；增加 source delimiters 与策略后复测。
3. 删除关键证据并提问，调节阈值观察“幻觉率 vs 拒答率”，理解没有免费的阈值。

### 退出条件

黄金集达到 MVP 门禁；引用可回原文且再次鉴权；无证据、安全攻击、模型失败有不同可理解的 UI；所有配置可版本化发布和回滚。

---

## S5. 企业管理、安全与治理（W11–W12）

### 目标与应用场景

补齐生产组织所需的 SSO 生命周期、细粒度权限、配额、审计、配置审批、知识发布治理和安全控制，使系统从“团队工具”变为“受控企业服务”。

### 需求

IAM 全部 M/S、ADM-001~007、UC-03/04，以及 [07](07-security-and-governance.md) 中 P0/P1 控制。

### 设计与实现

- 对接企业 IdP；映射组/角色，定义禁用、离职、组变化的传播时限；可选 SCIM。
- 权限 Policy Engine 集中化，API/Worker/引用/导出复用；高风险操作要求 reason/approval_id。
- Prompt/模型/检索配置实行草稿→评测→审批→发布→回滚；发布版本不可变。
- 租户/用户/服务账号配额：RPS、并发、日/月 token、费用、上传容量；提供预警和硬限制。
- 审计仅追加、受控查询和异步导出；日志字段白名单和隐私保留策略落地。
- 文件沙箱、出网 allowlist、secret manager、镜像签名/SBOM、依赖许可门禁。
- 完成 OWASP LLM 风险映射、红队用例和事件响应流程。

### 本阶段接口与字段

| 领域 | 接口/字段 |
|---|---|
| 用户/组 | `GET /users`, `GET /groups`, `PATCH /users/{id}`；`status,roles,group_ids,auth_subject`（高权限） |
| Prompt | `name,template,variables_schema,output_schema,checksum,status,version,approval_id` |
| 模型路由 | `provider_ref,model,capabilities,timeout_ms,fallback_routes,data_policy,price_snapshot` |
| 配额 | `scope_type,scope_id,period,request_limit,token_limit,cost_limit,currency,enforcement` |
| 审计 | `actor,action,resource,result,request_id,occurred_at,changes_safe,approval_id` |

管理接口不得返回 secret value、完整系统 Prompt 给无 `prompt:secret_read` 的角色，或未经审批的对话正文。

### 测试与验收

- RBAC + ABAC + ACL 全矩阵；权限缓存失效和离职用户时效。
- OWASP GenAI 风险用例：直接/间接 Prompt Injection、敏感信息泄露、供应链、数据投毒、输出处理、过度授权、资源耗尽等。
- 日志/Trace/错误响应密钥与 PII 扫描；审计篡改权限测试。
- 配额并发竞争、时钟边界、失败调用对账、管理员豁免审计。
- 配置未审批/评测失败不能发布；紧急回滚有双人流程和证据。

### 教学实验

1. 用普通用户、知识管理员、审计员三种 token 运行同一组 API，生成权限差异报告。
2. 在测试日志中注入假密钥/身份证样式字符串，验证扫描器与脱敏器告警。
3. 模拟一个恶意文档绕过 Prompt，按“预防—检测—响应—恢复”记录完整安全事件。

### 退出条件

安全评审无未缓解 P0/P1；租户/ACL/密钥/日志测试通过；配置与知识发布有审批和回滚；审计/数据负责人签字。

---

## S6. 质量、性能、可观测与容灾（W13–W14）

### 目标与应用场景

证明系统在目标负载、上游故障和数据恢复场景下满足 SLO，并把 AI 质量回归纳入标准发布流程。

### 需求

NFR 全部、ADM-005/006、[08](08-testing-and-evaluation.md)、[10](10-observability-and-operations.md)。

### 设计与实现

- OpenTelemetry 贯通 Gateway→API→Retriever→DB→Model Gateway→Provider，日志自动注入 trace ID。
- 质量、可靠性、延迟、成本四类仪表盘；避免将 tenant/user/question 作为高基数 metric label。
- CI 快速评测（20–50 条）+ 夜间完整集 + 发布候选固定集；报告配置差异和失败样本。
- 压测三类流量：稳态、峰值、摄取与聊天混合；SSE 连接和上游配额单独建模。
- 故障注入：Provider 429/超时、Redis 不可用、Worker 崩溃、DB failover、对象存储短暂错误。
- 备份、时间点恢复、对象版本/生命周期、配置和密钥恢复；执行 RPO/RTO 演练。

### 本阶段接口与字段

`POST /evaluations/runs`：`dataset_version_id,candidate_config_ids,baseline_run_id,tags`。  
`GET /evaluations/runs/{id}`：`status,metrics,thresholds,gate_result,failed_cases,cost,started_at,finished_at`。  
`GET /usage`：`from,to,group_by,tenant/model/operation filters`，返回 `requests,tokens,cost,error_rate`。  
管理指标 API 与监控后端分离，公开接口不直接暴露 Prometheus。

### 测试与验收

- 在目标稳态和 2 倍峰值下达到 SLO，无资源泄漏、队列无限增长或数据库连接耗尽。
- Provider 故障不会级联拖垮健康实例；熔断/恢复符合设计。
- 评测门禁能阻止一次故意降低质量的 Prompt 或检索配置。
- 从备份恢复到隔离环境，校验租户/文档/版本/向量/会话抽样一致，实测 RPO/RTO 达标。
- 告警每条都有 Owner、阈值依据、Runbook 和去重/抑制策略。

### 教学实验

1. 做一次“慢查询 → DB 连接堆积 → API 延迟”的 trace 排障，写 5 Why。
2. 注入主模型 100% 超时，观察断路器、备用模型、错误预算与用户体验。
3. 从空环境恢复数据库和对象，计算真实 RPO/RTO；不要把“备份成功”当“可恢复”。

### 退出条件

性能、质量、故障和恢复报告批准；生产告警经过测试触发；仪表盘可按版本比较；值班人员按 Runbook 完成一次演练。

---

## S7. UAT、灰度上线与运营移交（W15–W16）

### 目标与应用场景

使用同一不可变制品完成预生产 UAT、生产灰度、监控和逐步放量，并将系统交给稳定的产品与运维机制。

### 发布步骤

1. 冻结候选版本，生成 SBOM、签名镜像、迁移计划、评测/测试报告和已知问题。
2. 在 staging 从生产同类备份结构做迁移演练；验证 expand/contract 和回滚/前向修复。
3. 业务代表完成 UC-01~05 UAT；安全、SRE、数据、产品签署发布清单。
4. 生产先部署暗流量/内部测试租户，再 5% → 25% → 50% → 100% 放量；每档至少观察一个完整业务高峰或约定窗口。
5. 自动比较错误率、TTFT、完整延迟、拒答、差评、引用、成本和安全事件；超过阈值自动停止或回滚。
6. 完成发布后观察期、复盘、知识移交和下一阶段 backlog。

### 本阶段接口与字段

外部 v1 契约冻结；只允许兼容性修复。发布记录至少含：`release_id, git_sha, image_digest, db_migration, prompt_versions, retrieval_versions, model_route_versions, dataset_version, eval_run_id, approvers, rollout_stage, rollback_target`。

### 培训与文档

- 用户：如何提问、核对引用、识别拒答、提交有效反馈。
- 知识管理员：文档质量、ACL、预览、发布、回滚、评测失败处理。
- 开发：本地启动、契约、模块边界、调试和 PR 规范。
- SRE：仪表盘、告警、扩容、供应商故障、队列积压、恢复和升级。
- 安全/审计：事件查询、导出审批、封禁、证据保全和数据请求。

### 验收与退出条件

- 所有 M 需求、UAT、质量/性能/安全/DR 门禁通过，P0/P1 为 0。
- 灰度期间 SLO、质量、成本无显著退化，回滚演练在目标时间内完成。
- 生产 Owner、on-call、供应商联系人、预算和续费/密钥轮换计划明确。
- 文档、源代码、IaC、镜像、SBOM、测试证据、仪表盘、Runbook 和风险接受项完成移交。

---

## 3. 每个 Sprint 的节奏

| 时间 | 活动 | 输出 |
|---|---|---|
| Sprint 前 | Refinement、数据/威胁影响识别 | 满足 DoR 的故事 |
| Day 1 | Planning、接口与 Owner 明确 | Sprint goal、任务与风险 |
| 每日 | 15 分钟同步，阻塞升级 | 可见进展 |
| PR 前 | 自测、契约、迁移、监控和文档 | 可审查 PR |
| 中期 | 架构/质量风险检查 | 决策和调整 |
| 末期 | Demo 正常+失败路径、验收 | 接受/退回 |
| Retro | 过程与质量复盘 | 1–2 个可执行改进 |

## 4. 教学方式建议

- 每个实验先用最小代码观察机制，再按生产规范重构；实验分支不直接合并。
- 教学不只讲“怎么调 API”，还要让学习者制造并修复跨租户、重复任务、流中断、Prompt 注入和恢复失败。
- 每阶段写一页学习日志：假设、实验、指标、失败、决策、下一步。把“我觉得更好”转成可复现证据。
- 新工程师的结业任务是从上传一份合成制度到完成带引用问答，并能通过 trace 解释每个耗时和成本字段。

## 5. 进度压缩原则

若团队更小或只有 8–10 周，不删除安全边界和评测，而是缩小业务面：只做单场景、单渠道、2 种文件、1 个主模型+Fake Provider、固定系统角色、pgvector、Compose+一个托管预生产环境。可以延后 Kubernetes、多连接器、复杂管理台和多模型自动路由，但不能延后租户/ACL、引用、拒答、审计基础和恢复验证。

## S3 实施完成记录（2026-07-16）

S3 已按本计划完成合成开发基线，详细实现、接口、教学、风险和 Gate 以 [S3 证据包](s3/README.md) 为准。相对原计划的显式选择：任务真相源采用 PostgreSQL lease + outbox，而非提前引入 Celery broker；S3 vector 暂存 JSON 且检索只做 ACL 后词项调试，pgvector/hybrid 正式检索留到 S4；生产扫描强制 ClamAV，本地签名 scanner 不可作为上线控制。

最终证据为 45 tests、86% 总覆盖率、Ruff/Mypy/ESLint/迁移/契约/依赖审计通过，API/Worker/Web 干净镜像构建通过，且 PostgreSQL/Redis/MinIO/OIDC/浏览器签名直传/Worker/ACL 调试检索的隔离 Compose smoke 通过。Helm CLI/集群安装、真实 S3/ClamAV/Embedding、真实文档 UAT、多 Worker 压测仍是生产阻断。
