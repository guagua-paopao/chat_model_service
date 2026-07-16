# S4 决策日志

| 日期 | 决策 | 理由 | ADR/证据 | 复审触发器 |
|---|---|---|---|---|
| 2026-07-16 | 两个召回分支均在 SQL 安全集合内执行 | 防止存在性泄漏和无权结果占 top-k | ADR-025、ACL 测试 | 引入专用向量库/跨库检索 |
| 2026-07-16 | PostgreSQL 用 pgvector + FTS；SQLite 只做测试回退 | 兼顾事务边界与快速回归 | ADR-025、Compose smoke | 规模超出 PostgreSQL 证据 |
| 2026-07-16 | 使用 weighted RRF 后再 rerank | 原始 vector/FTS 分数不可直接比较 | ADR-025、评测脚本 | 新 fusion 离线显著改善 |
| 2026-07-16 | RAG config 发布后不可变，run/hit 全量快照 | 让调参和回答可复现 | ADR-026、0004 migration | 管理/审批工作流上线 |
| 2026-07-16 | grounded 模型输出缓冲到引用校验完成 | 防止无效/伪造回答提前外泄 | ADR-027、SSE 集成测试 | 支持可验证增量协议 |
| 2026-07-16 | 模型引用只能使用本次服务端 Source ID | 不信任模型生成文档 ID/URL | ADR-027、invalid citation test | claim-level structured protocol |
| 2026-07-16 | Citation 是不可变快照，但每次详情按当前 ACL 再鉴权 | 同时满足历史审计和即时撤权 | ADR-028、ACL 撤销测试 | 法律删除/保留策略变化 |
| 2026-07-16 | evidence/safety abstention 不调用模型 | 降低泄漏、幻觉和成本 | ADR-029、invocation count 测试 | 引入安全分类器需重新审批 |
| 2026-07-16 | 权限不可见与无资料使用相同外部语义 | 防止 KB/文档存在性探测 | ADR-029、跨租户 404 | 安全团队批准差异化 UX |
| 2026-07-16 | SOURCE 永远是不可信数据；可疑指令句从 context 移除 | Prompt 文字本身不足以防间接注入 | ADR-030、注入测试 | 新 sandbox/content firewall |
| 2026-07-16 | 默认 query coverage 从 0.20 提到 0.34 | 首轮 N02 因泛词 employees 误答 | 20-case 前后评测 | 真实 dev/test 集校准 |
| 2026-07-16 | 暂用精确 vector scan，不建 ANN | 向量列维度/容量未冻结，优先正确性 | ADR-031 | 固定模型维度和负载数据 |
| 2026-07-16 | 暂不做 semantic cache | 未证明 ACL/版本/config key 和失效安全 | ADR-032 | 完成侧信道与撤权设计 |
| 2026-07-16 | confidential/restricted 禁止外部 Embedding/Reranker | 默认最小外发 | config/RAG guard | 数据 Owner 和供应商书面批准 |
| 2026-07-16 | Fake Embedding 升级为 v2/s4-v1并要求本地重建 | 语义词袋替代整段 hash，旧向量不可混用 | ingestion/RAG tests | embedding adapter 版本变化 |
| 2026-07-16 | Feedback 与回答/检索/模型快照绑定 | 避免后续配置变化污染质量分析 | 0004、feedback test | 隐私/保留政策变化 |
| 2026-07-16 | Web 明确区分系统失败、资料不足和安全策略 | 用户可采取不同动作，内部仍防侧信道 | UI/SSE design | 用户研究/安全复审 |
| 2026-07-16 | S4 只本地提交，不自动发布 GitHub | 完整公开仓库需要用户逐阶段明确授权 | 用户阶段流程 | 用户明确确认公开 S4 |
