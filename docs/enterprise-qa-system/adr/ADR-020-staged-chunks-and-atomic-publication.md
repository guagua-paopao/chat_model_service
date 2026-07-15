# ADR-020：Staged chunks 与数据库原子发布

- 状态：Accepted
- 日期：2026-07-16
- 关联：ADR-006

## 背景

解析、向量化和对象复制会部分成功。直接逐 chunk 写 active 会让检索看到半版本；原地覆盖旧版本破坏审计和引用。

## 决策

版本不可变。Worker 先为目标 version 写 `status=staged,is_active=false` chunks；对象复制到 published 成功后，在一个数据库事务中归档该 document 的旧 active chunks、发布目标 chunks、更新 current_version、版本 provenance 和 job。事务完成后再尽力删除 quarantine。

对象复制与 DB 无分布式事务。选择“先复制、后 DB 发布”：DB 失败只会产生不可检索 orphan，不会产生指向不存在对象的已发布版本。后续 reconciliation/lifecycle 清理 orphan。

## 后果

新版本失败时旧版本继续可用；重跑可删除并重建 inactive staged chunks。代价是额外存储、清理任务和 DB 发布事务竞争；S4/S5 需增加 reconciliation、保留与告警。

