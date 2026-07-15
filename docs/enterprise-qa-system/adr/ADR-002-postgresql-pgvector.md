# ADR-002：PostgreSQL + pgvector 作为首版检索存储

- Status：Accepted
- Decision date：2026-07-15
- Owners：Architecture / Data / Backend
- Review date：S3 真实数据压测后

## Context

首版需要同时根据租户、知识库、文档状态、版本、ACL 和业务元数据过滤，再进行全文与向量召回。团队希望降低独立向量库和事务同步的运维成本。

## Decision

使用 PostgreSQL 保存事务数据、全文索引和 pgvector 向量。首版固定一个 Embedding 维度（参考 DDL 为 1536）；不同维度/模型通过新索引版本重建，不在同列混写。关键词与向量候选在授权范围内召回，再融合/重排。

## Alternatives

- Milvus/Weaviate/Qdrant：向量规模与专用能力更强，但增加一致性与运维边界。
- OpenSearch/Elasticsearch：混合检索成熟，但权限/主数据仍需同步。
- 仅向量/仅全文：实现简单，但错误码、专有名词或语义问题召回不足。

## Consequences

优点：ACL 和元数据可在同一查询计划中生效，版本发布可用数据库事务，备份/审计边界较少。缺点：向量索引会增加存储、内存和维护压力；需针对 HNSW/查询计划压测。

## Security and Cost

同库降低复制泄露面，但应用账号必须 tenant-scoped、最小权限；生产可启用 RLS 双保险。索引和备份容量按 S0 成本模型规划。

## Review Triggers

向量达到数千万且 P95/召回/写入不达门槛、索引维护显著影响 OLTP、需要独立扩缩或专用检索功能时，使用真实评测集对专用引擎做 PoC，不能只以规模宣传替换。

