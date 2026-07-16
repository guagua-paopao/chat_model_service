# 灰度、门禁与回滚

## 状态顺序

`none → dark → percent_5 → percent_25 → percent_50 → percent_100`。禁止跳级；每次 advance 评估前一阶段窗口。

## 服务端门禁

| SLI | 通过阈值 |
|---|---:|
| server error rate | ≤ 1% |
| TTFT P95 | ≤ 2500 ms |
| 完整回答 P95 | ≤ 15000 ms |
| 负反馈率 | ≤ 10% |
| 引用精度 | ≥ 90% |
| 成本差异 | ≤ +10% |
| 质量差异 | ≥ -2% |
| 安全事件 | 0 |
| 未授权泄漏 | 0 |

一般退化执行 `auto_stop` 并冻结当前阶段；安全事件或未授权泄漏执行 `auto_rollback`。人工 stop/rollback 要求 Release Manager 权限、审批 ID 和理由。

## 事件字段

`sequence_no,action,from_stage,to_stage,decision,observation,reason,actor_user_id,previous_hash,event_hash,occurred_at`。哈希链验证失败时不得继续放量。

本地 observation 是合成输入。生产控制器必须从批准的 Prometheus/APM/质量/成本/安全系统读取可信信号，并将部署 ID、集群、镜像 digest 和原始查询链接写入证据平台。
