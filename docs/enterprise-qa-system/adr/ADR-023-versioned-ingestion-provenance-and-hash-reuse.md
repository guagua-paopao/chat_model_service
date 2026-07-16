# ADR-023：摄取 Provenance 版本化与受限哈希复用

- 状态：Accepted
- 日期：2026-07-16

## 背景

解析库、规范化、分块参数和 Embedding 变化会改变检索结果。如果只保存最终向量，无法解释差异、重建或回滚。重复内容重新 Embedding 又浪费时间和成本。

## 决策

每个 document_version 保存 parser version、chunker version、embedding model/version/dimensions、page/chunk/token count 和实际 hash/MIME/size。Chunk 保存 normalized content hash 和结构 provenance。

Embedding 可按内容 hash 复用，但只能在同 tenant、同 model、相同 dimensions 内；每批最多 32。算法或依赖主版本改变时递增 provenance，通过新版本/重建发布，不原地改变已发布版本语义。

## 后果

支持比较、回归、成本优化和审计；代价是元数据与重建管理。跨 tenant 中央缓存被拒绝，以避免侧信道、数据治理和删除语义复杂化。

