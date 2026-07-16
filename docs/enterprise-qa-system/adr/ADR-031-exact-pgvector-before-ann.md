# ADR-031：先用精确 pgvector 建立正确性基线，再选择 ANN

- 状态：Accepted
- 日期：2026-07-16

## 背景

ANN 索引需要固定向量维度、数据规模、过滤选择性和 recall/latency 目标。S4 尚未批准生产 embedding 或取得真实容量数据。

## 决策

S4 PostgreSQL 使用 `VECTOR` 列和精确 cosine 扫描，候选/上下文有硬上限；不创建 HNSW/IVFFlat。批准固定模型后，在 ACL 过滤条件下比较 exact、HNSW 和 IVFFlat 的 Recall@10、P95、内存、构建/更新成本，再提交索引 ADR。

## 后果

避免以未知参数过早优化并提供正确性 oracle；大规模性能不达标是明确生产阻断，不得用小型 smoke 关闭。
