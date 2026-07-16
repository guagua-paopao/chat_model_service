# ADR-025：在 ACL 安全集合内执行双通道召回与融合

- 状态：Accepted
- 日期：2026-07-16

## 背景

向量检索覆盖语义近似，全文检索覆盖编号、名称和精确词；两者原始分数不可比。任何先全局 Top-K 再过滤 ACL 的实现都会泄漏存在性并降低有权召回。

## 决策

PostgreSQL 的 pgvector cosine 与 FTS 分支均先约束 tenant、KB、published current active version、未删除文档和 user/role ACL，再取候选。使用 weighted reciprocal rank fusion 合并 rank，之后对受限候选做版本化 rerank。SQLite 只提供使用相同安全集合的确定性测试回退。

## 后果

安全顺序和分数融合可解释、可测试；代价是 SQL 和索引设计更复杂，FTS tokenizer 与 ANN 必须另行评测。引入独立向量库时仍必须证明等价 ACL 前置语义。
