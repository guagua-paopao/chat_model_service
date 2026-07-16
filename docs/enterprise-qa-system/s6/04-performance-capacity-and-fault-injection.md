# 性能、容量与故障注入

## 1. 压测场景

| Profile | 默认速率/时长 | 内容 | 用途 |
|---|---:|---|---|
| smoke | 1 RPS / 10 s | authenticated `/models` | 连通性 |
| steady | 10 RPS / 60 s | API | 稳态基线 |
| peak | 50 RPS / 60 s | API | 初始峰值假设 |
| mixed | 10 RPS / 60 s | 90% API + 10% SSE | 混合路径 |
| sse | 2 RPS / 30 s | conversation + stream | TTFT/完整耗时 |

工具保护：默认仅 localhost；100 RPS、300 秒、64 并发硬上限；非本地必须 `--allow-nonlocal`；Bearer 不打印。目标环境测试还必须有变更单、Owner、预算、监控、停止阈值和数据清理方案。

## 2. 本地结果

2026-07-16 的短时 smoke：2 RPS、3 秒、6 请求、成功率 100%、实际 2.0 RPS、P95 74.88 ms。样本过小且只访问 Fake/本地 API，不能证明 50 RPS 或 200 SSE 生产目标。

## 3. 故障矩阵

| 故障 | 注入 | 预期 | 本地结果 |
|---|---|---|---|
| Primary 429 | `[429]` | 有界重试并切 backup | 200 / fake-backup |
| 全路由 429 | `[all-429]` | 429 Problem，不无限重试 | 通过 |
| Primary timeout | `[timeout]` + 0.1s 首 token | 取消并切 backup | 200 / fake-backup |
| Provider 无 usage | `[missing-usage]` | 标记 estimated 并入账 | 通过 |
| 故障后健康请求 | 普通请求 | 无熔断污染 | 200 |

## 4. 目标环境计划

逐项执行 Redis 不可用、Worker kill、数据库连接耗尽/主备切换、对象存储超时、Provider 区域故障、Collector 不可用和 Ingress SSE 断线。每项记录影响面、自动恢复、数据一致性、重试风暴、告警到达、RTO 和人工步骤。

## 5. 容量计算教学

Little’s Law：并发约等于吞吐 × 平均停留时间。若 10 RPS 的平均 SSE 会话持续 12 秒，基础并发约 120；再乘峰值和故障余量。CPU/内存/连接池必须从目标集群压测获得，不能用开发机结果配置生产副本数。
