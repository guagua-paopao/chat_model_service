# S4 需求与范围

## 1. 阶段目标

在 S1 身份/租户、S2 模型网关和 S3 不可变知识摄取基础上，完成“提问 → 授权检索 → 重排 → 证据构造 → 有依据生成/拒答 → 引用 → 反馈 → 审计”的纵向闭环。S4 的成功标准是安全与可回归，不是把合成演示称为生产 RAG。

## 2. 角色与应用场景

| 角色 | 场景 | 期望结果 |
|---|---|---|
| 员工 | 查询差旅、休假、IT 制度 | 只基于其有权知识回答，每个事实附引用 |
| 支持人员 | `search_only` 排查原始证据 | 不调用模型，返回排序后的受控片段 |
| 知识管理员 | 发布资料后验证可检索性 | 新版本原子可见，旧版本不进入新回答 |
| 安全/审计 | 复盘一次回答 | 找到检索配置、候选、ACL 指纹、Prompt/模型和引用快照 |
| 产品/质量 | 提交好评或问题标签 | 反馈与回答快照绑定，可用于离线评测而不篡改历史 |

## 3. 功能需求

| ID | 需求 | 验收 |
|---|---|---|
| S4-F01 | 三种回答模式 | general 不访问知识；grounded 生成引用答案；search_only 零模型调用 |
| S4-F02 | 多 KB 选择 | 1–10 个 KB，必须同租户且 active；不可见 KB 返回安全 404 |
| S4-F03 | 双通道召回 | PostgreSQL pgvector cosine + FTS；SQLite 仅作确定性测试回退 |
| S4-F04 | 安全候选集合 | tenant/current/published/active/deleted/KB/ACL 过滤先于排名 |
| S4-F05 | 融合与重排 | 版本化 weighted RRF、rerank candidate 和 final-k |
| S4-F06 | 上下文构造 | 去重、相邻块合并、token 预算、受控 Source ID、provenance |
| S4-F07 | 证据门槛 | 最低相关度与查询词覆盖率；不足时拒答且不调用模型 |
| S4-F08 | Grounded 输出 | 模型输出必须至少引用一个本次 Source ID；未知 ID fail closed |
| S4-F09 | 引用溯源 | 回答返回文档/版本/页码/章节/quote/分数；详情每次重新鉴权 |
| S4-F10 | 注入控制 | Query 直接攻击拒绝；文档被视为数据，命中可疑句子从上下文移除 |
| S4-F11 | 审计快照 | 记录 run/hit/config/prompt/model/embedding/reranker/ACL/知识版本 |
| S4-F12 | 反馈 | 每用户每消息 upsert，保存 rating/reason/comment 与回答快照 |
| S4-F13 | Web 闭环 | 模式、检索状态、拒答/安全/故障、引用详情、反馈清晰可见 |

## 4. 非功能需求

- 安全：越权文档标题、分数、片段、存在性和引用 URL 均不得泄漏。
- 可复现：相同知识版本、配置版本、Fake 模型和输入产生确定结果。
- 可追踪：每次知识回答具有 `retrieval_run_id`，配置为 immutable published row。
- 可靠性：Reranker 超时、协议错误、引用验证失败均 fail closed；错误文案不含供应商正文或密钥。
- 性能：候选数和 context budget 有硬上限；S4 未完成目标容量压测，不声明 P95 达标。
- 隐私：retrieval run 仅存 query SHA-256，不在普通日志或审计详情保存原问题正文。

## 5. 验收场景

1. 已授权制度问题命中正确文档，回答含有效 `[SRC-nnn]`，引用详情可重新鉴权打开。
2. 同一问题由无文档 ACL 的用户发起，返回证据不足/安全不可见，不泄漏文档元数据。
3. 发布新版本后新请求只使用当前版本；历史 citation 快照保持不可变。
4. 文档包含“ignore previous instructions”，模型上下文剔除该句，回答不回显或执行命令。
5. Fake 模型输出 `[SRC-999]`，客户端只看到安全拒答，不看到未经验证的 token。
6. `search_only` 返回引用且 model invocation 数不增加；无证据请求同样零调用。
7. 撤销 ACL 后引用详情返回安全 404；恢复后可再次查看同一不可变快照。
8. 跨租户 KB ID 探测返回 404，retrieval hits 为零。
9. 20 条合成门禁达到 Recall@10、Groundedness、Citation、Abstention 阈值且泄漏为零。

## 6. 非目标

- 不做多轮 query rewriting、GraphRAG、Agent 工具调用、多模态或联网搜索。
- 不提供文档原件预签名下载；S4 只返回受控引用预览。
- 不启用 semantic cache；尚未证明 ACL/版本/配置键和失效协议安全。
- 不做 ANN/HNSW 生产索引；当前向量维度由 Provider 配置，先使用精确扫描取得正确性证据。
- 不声称启发式注入过滤或 Source ID 校验等价于完整 claim-level factuality/NLI 验证。
- 不关闭 S0–S3 的真实数据、IAM、存储、扫描、共享配额、Kubernetes、SLO 和 DR 阻断项。
