# ADR-021：数据库租约任务与 Outbox

- 状态：Accepted
- 日期：2026-07-16

## 背景

S3 需要独立异步 Worker、幂等恢复和可审计状态，但当前规模没有证据支持引入额外 broker，并且 DB+broker 双写会产生新的不一致。

## 决策

`ingestion_jobs` 是任务真相源。PostgreSQL Worker 以 `FOR UPDATE SKIP LOCKED` 领取 queued job，写 lease owner/until 和 attempt；过期 running job 可重领。可重试失败指数退避，耗尽 dead_letter。completion 使用派生幂等键；操作员 retry 强制 `Idempotency-Key` 并创建新 job。

同一事务写 outbox 表，用于事件审计和未来消息总线发布；S3 Worker 不依赖 broker 消费 outbox。

## 后果

实现简单、因果状态可查询、避免 DB/broker 双写。代价是 DB 轮询负载、长任务续租和高吞吐边界；多 Worker 压测或吞吐需求触发重新评审，可加 outbox relay/broker，但 job 仍应保持幂等真相。

