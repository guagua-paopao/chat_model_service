# ADR-043：进程快照、用量账本与 SLO 证据分层

- 状态：Accepted
- 日期：2026-07-16
- Owner：Platform / FinOps / SRE

## 决策

- `/usage` 从追加式账本聚合，最大查询窗口 31 天，可按 model/operation 分组，服务于计量和 FinOps。
- `/admin/operations/snapshot` 返回当前 API 实例最近 5 分钟请求样本和租户级数据库信号，只服务于快速诊断。
- Prometheus 保存跨实例时序并作为 SLO 计算来源；任何单进程快照都不得作为生产可用性证明。
- 三层均不返回原始 query、prompt、答案或文档正文。

## 后果

财务、排障和 SLO 语义不再混用；正式财务结算仍需供应商账单对账和汇率/税务流程。
