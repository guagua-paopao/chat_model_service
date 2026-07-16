# ADR-018：多副本生产前必须共享配额与取消状态

- Status：Accepted
- Decision date：2026-07-15
- Owners：Platform / API / SRE
- Review trigger：Redis 协调实现完成或部署拓扑变化

## Context

S2 为教学和单进程验证实现了内存请求速率、tenant/user 并发信号量和活动取消注册表。Helm 目标为多副本；各 Pod 独立计数会放大配额，取消请求也可能落到错误 Pod。

## Decision

当前内存实现只允许 local/test/dev 和单副本合成环境。任何 staging/production 多副本发布前，必须将速率、并发租约和取消信号迁移到 Redis 或等价共享协调层，具有原子获取/释放、租约 TTL、崩溃恢复、幂等取消和故障降级测试。

在该控制完成前，S2 Gate 不批准生产。临时用会话粘滞或单副本不能作为生产风险关闭证据，除非经过正式、限期的风险接受。

## Consequences

开发链路保持可学习和可测试，但生产 readiness 被明确阻断。后续实现应保留当前接口，使共享后端可替换而不改变聊天 API。
