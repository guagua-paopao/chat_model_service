# ADR-022：ACL 必须先于评分和 Top-K

- 状态：Accepted
- 日期：2026-07-16

## 背景

先全局检索再过滤 ACL 既可能泄露分数/存在性，又会让无权高分结果占用 top-k，损害有权召回。管理员 API 权限也不等于文档读取授权。

## 决策

检索候选集在数据库/索引层同时约束 tenant、published current active version、KB 范围和 document ACL，之后才评分、融合、rerank 和 top-k。S3 支持可信 user ID 与 role code；Principal 尚无可信 group 时 group ACL fail closed。管理员不自动绕过文档 ACL。

缓存键未来必须包含 tenant、ACL/subject 指纹和 knowledge version；引用打开时再次鉴权。

## 后果

安全边界清晰并保持有权召回。代价是 ANN/缓存设计更复杂；S4 引入 pgvector/hybrid 时必须保留 SQL/安全候选约束并执行正负权限矩阵。

