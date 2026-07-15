# 08. 测试与 AI 评测

## 1. 总体策略

传统软件测试回答“系统是否按确定性契约运行”，AI 评测回答“在固定数据与配置下，概率性输出是否达到业务门槛”。两者缺一不可。测试环境使用 deterministic fake providers 保证故障与协议可重复，另用批准的真实模型运行质量集。

```text
大量：单元测试 / schema / policy / parser fixture
中量：数据库、队列、对象存储、模型适配器契约集成测试
少量：浏览器 E2E、真实供应商沙箱、性能、故障、安全、UAT
贯穿：RAG 离线评测 + 线上质量/反馈监控
```

## 2. 测试分层

### 2.1 单元测试

- Policy Engine：角色、组、ACL、租户、资源状态的允许/拒绝矩阵。
- 切分：标题、段落、表格、超长、空白、Unicode、页码映射 fixture。
- 检索融合：RRF、去重、相邻合并、token 预算、阈值与拒答。
- Model Gateway：错误归一化、重试判定、路由、fallback、token/成本计算。
- 状态机：消息、文档、任务、配置发布的合法/非法转换。
- 数据验证：元数据白名单、文件类型、ID/时间/金额、幂等 request hash。

关键业务模块行覆盖建议 ≥80%，但发布依据是风险场景覆盖，不是只追求总行数。授权/租户/配额/迁移的关键分支应 100% 覆盖设计场景。

### 2.2 集成与契约测试

- 使用真实 PostgreSQL+pgvector、Redis、S3 兼容存储容器，不用内存假实现替代全部语义。
- OpenAPI request/response schema 验证；Web/SDK 消费者驱动契约。
- 每个 Model Adapter 跑统一 Provider Contract Suite：流、usage、取消、429、超时、内容过滤、无效 key。
- Outbox 至少一次、重复投递、乱序、Worker 重启、死信与幂等。
- 数据库迁移从上一个生产版本升级，并验证前一版本应用与 expand 阶段兼容。

### 2.3 E2E

1. OIDC 登录 → 创建会话 → 提问 → 流式渲染 → 打开引用 → 反馈。
2. 管理员创建 KB → 上传 → 观察任务 → 预览 → 发布 → 问答命中。
3. 上传错误文件 → 失败说明 → 修复/重试。
4. Prompt/检索候选配置 → 评测 → 审批 → 发布 → 回滚。
5. 禁用用户/修改 ACL → 旧会话引用再次鉴权失败。

E2E 不依赖真实收费模型的随机输出，默认用可编程 fake；另设少量真实 Provider smoke test，不阻塞所有 PR。

## 3. RAG 评测数据集

### 3.1 数据集分层

| 切片 | 用途 | 例子 |
|---|---|---|
| answerable | 正常问答 | 制度条款、产品参数 |
| no_answer | 正确拒答 | 资料未覆盖、未来政策 |
| ambiguous | 需要澄清 | 缺少地区/版本/产品 |
| acl | 权限边界 | 来源存在但当前角色无权 |
| outdated/conflict | 版本与冲突 | 新旧制度、多个来源矛盾 |
| lexical | 精确词匹配 | 错误码、合同编号、缩写 |
| semantic | 同义/口语 | “住宿能报多少” |
| table/numeric | 表格与数字 | 城市等级、费用上限 |
| multilingual | 多语言 | 中文问题/英文手册 |
| injection/safety | 攻击与滥用 | 文档内隐藏指令、Prompt 诱取 |

### 3.2 推荐字段

```json
{
  "case_id": "POLICY-001",
  "dataset_version": "2026.07.1",
  "tenant_code": "demo_corp",
  "persona": "employee",
  "question": "一线城市住宿费上限是多少？",
  "conversation_history": [],
  "knowledge_base_codes": ["travel_policy"],
  "expected_answer_points": ["上限数值", "适用城市等级", "生效日期"],
  "expected_source_ids": ["travel-policy:v3:p8"],
  "forbidden_source_ids": ["salary-policy:v1"],
  "answerable": true,
  "expected_behavior": "answer",
  "risk_tags": ["numeric", "citation", "version"],
  "notes": "数值以 v3 为准",
  "reviewed_by": ["business_owner_a", "qa_reviewer_b"]
}
```

数据集版本不可变，变更生成新版本；训练/调优集与最终 holdout 集分离。不要让评测问题出现在 Prompt 示例中造成泄漏。

## 4. 指标定义

### 4.1 检索指标

- **Recall@k**：具有任一正确证据的问题中，top-k 是否包含正确 chunk/document。
- **MRR**：首个正确证据排名倒数的平均值，关注正确结果是否靠前。
- **nDCG@k**：有多级相关性标注时衡量排序质量。
- **ACL precision**：返回候选全部属于授权、当前发布版本；必须 100%。
- **context utilization**：最终回答实际引用证据占 selected context 的比例，诊断上下文浪费。

文档级 Recall 较容易但会掩盖 chunk 不完整；至少同时报告 document 和 chunk/answer-span 级结果。

### 4.2 生成与引用指标

| 指标 | 含义 | 评估方式 |
|---|---|---|
| Answer correctness | 是否覆盖预期事实且无错误 | 规则/人工/模型裁判组合 |
| Groundedness/Faithfulness | 可验证事实是否被证据支持 | claim 分解后逐条核对 |
| Answer relevance | 是否回答用户意图 | 人工或 rubric judge |
| Citation precision | 被引用来源是否真的支持相邻主张 | claim-source 标注 |
| Citation completeness | 需要证据的主张有多少被引用覆盖 | claim-source 标注 |
| Abstention precision | 拒答中有多少确实应该拒答 | no-answer 标签 |
| Abstention recall | 应拒答问题有多少被拒答 | no-answer 标签 |
| Safety attack success | 攻击是否导致泄露/越权/违规工具调用 | 安全 oracle；越低越好 |

模型裁判必须固定 judge 模型、Prompt、温度和 rubric，定期用人工样本校准；judge 不是绝对真值。数字、日期、引用 ID、权限等优先用确定性规则。

### 4.3 工程与成本指标

- TTFT P50/P95/P99、完整响应 P95、检索/重排/模型分段耗时。
- 成功率、取消率、流中断率、Provider 429/5xx、fallback 率。
- 摄取端到端/各阶段耗时、失败/重试/死信、chunk 与 token 规模。
- 每答案输入/输出 token、Embedding token、成本 P50/P95、缓存命中。
- CPU/内存、DB 连接、慢查询、队列深度、SSE 并发和 Pod 重启。

## 5. 发布门禁

首版建议门槛（S0 用真实数据校准）：

| 类别 | 指标 | 门槛 |
|---|---|---:|
| 安全 | 跨租户/ACL 成功越权 | 0 |
| 检索 | Recall@10 | ≥ 0.85，且比生产基线不下降 >2pp |
| 生成 | Groundedness | ≥ 0.90 |
| 引用 | precision/completeness | ≥ 0.90 / ≥ 0.85 |
| 拒答 | no-answer F1 | ≥ 0.85 |
| 安全 | 高危攻击成功 | 0；总体不高于批准阈值 |
| 可靠性 | 核心 API 成功率（受控压测） | ≥ 99.9% |
| 性能 | TTFT P95 / total P95 | ≤ 2.5s / 15s（基线场景） |
| 回归 | 核心切片显著退化 | 无未经批准退化 |
| 成本 | 单答案 P95 | 不超过业务批准预算 |

不能用整体平均分掩盖 `acl/no_answer/numeric` 等关键切片。任何安全切片失败都是硬门禁；业务可对非安全小幅质量退化做有时限的风险接受。

## 6. 评测执行层级

| 层级 | 触发 | 数据量 | 用途 |
|---|---|---:|---|
| PR 快速集 | 影响 RAG/Prompt/Model 的 PR | 20–50 | 发现明显回归；fake + 少量真实 |
| 夜间集 | 每晚 | 200–1000 | 完整切片、重复运行估计波动 |
| 候选发布集 | 发布/配置发布 | 固定 holdout | 硬门禁与基线比较 |
| 知识发布集 | 文档/KB 新版本 | 受影响场景 | 防止内容/解析退化 |
| 线上抽样 | 连续 | 经批准的脱敏样本 | 检测分布漂移和真实失败 |

评测运行记录代码 SHA、镜像、数据集、知识版本、Prompt、检索、Embedding、reranker、模型路由/实际模型、温度、时间、成本和原始结果引用。

## 7. 性能与容量测试

### 7.1 负载模型

不要只做 HTTP 短请求 RPS。至少包含：

- 60% 新问题流、25% 继续会话、10% 引用详情、5% 管理/反馈。
- SSE 连接持续 5–30 秒，用户中途取消与断线。
- 同时运行文档解析/Embedding，验证资源隔舱。
- 热门/长尾问题、短/长上下文、缓存命中/未命中。
- 稳态 60 分钟、2 倍峰值 30 分钟、阶梯加压到破坏点、4–8 小时 soak。

### 7.2 通过条件

目标负载下满足 SLO，错误无不受控增长；无连接/内存泄漏；DB/Redis/队列/Provider 均有 ≥30% 合理余量；HPA 不因 SSE/自定义指标错误振荡；达到保护阈值时优雅 429/503 而非 OOM。

## 8. 安全测试用例族

| ID 前缀 | 用例 |
|---|---|
| SEC-TENANT | 猜测其他租户 UUID、缓存、任务、引用、导出、对象 URL |
| SEC-ACL | 用户/组/角色变化、撤权时效、历史引用、后过滤陷阱 |
| SEC-AUTH | 错 issuer/aud/alg、过期、重放、禁用、服务账号 scope |
| SEC-UPLOAD | MIME 伪造、宏、路径穿越、XML 外部实体、压缩炸弹、恶意 PDF |
| SEC-PROMPT | 直接/间接注入、系统 Prompt/密钥/其他来源诱取、多轮绕过 |
| SEC-OUTPUT | XSS/Markdown URL/CSV 公式/代码执行/SQL 注入 |
| SEC-DOS | 超长问题、token 爆炸、大文件、并发、重试风暴、工具循环 |
| SEC-SUPPLY | 漏洞依赖、篡改镜像、未签名制品、限制性许可证 |

渗透和红队必须在有授权的隔离环境执行，使用合成密钥和数据；测试产生的恶意样本进入永久回归集。

## 9. 故障与恢复测试

- Model：首 token/中途超时、429、5xx、错误 usage、流格式损坏、内容过滤。
- DB：慢查询、连接耗尽、主备切换、只读、迁移锁。
- Redis/队列：不可用、延迟、重复/乱序、积压、死信。
- Object：上传完成但对象缺失、hash 不符、读取超时、生命周期误配。
- Worker：每个阶段 kill -9、重启、任务过期、部分 Embedding。
- K8s：Pod/Node/可用区故障、滚动更新、优雅终止、DNS 异常。
- 恢复：数据库 PITR、对象版本、配置/Prompt、索引重建、密钥轮换后的恢复。

每次测试记录预期、实际、用户影响、检测时间、恢复时间、数据一致性和改进项。

## 10. 缺陷分级

| 级别 | 例子 | 发布规则 |
|---|---|---|
| P0 | 跨租户泄露、密钥暴露、数据不可恢复、广泛不可用 | 立即停止发布/回滚/事件响应 |
| P1 | 核心问答不可用、严重错误答案且无拒答、ACL 撤权失效 | 不可上线 |
| P2 | 部分格式失败、明显性能退化、有替代路径 | 有 Owner/期限和风险接受方可上线 |
| P3 | UI/文案/低频体验问题 | 进入 backlog |

AI 质量缺陷必须保存问题、允许证据 ID、配置版本、实际输出、期望 rubric 和重现运行；不要只贴聊天截图。

## 11. 测试报告最小内容

构建/版本、环境、数据集/知识版本、覆盖范围、通过/失败/跳过、指标及置信区间、失败切片、性能资源曲线、安全与许可、已知风险、豁免、签字和证据链接。报告不得嵌入未脱敏生产问题或完整受限文档。

