# S6 决策日志

| ID | 决策 | 理由 | 影响 |
|---|---|---|---|
| S6-D01 | 评测运行保存不可变数据集/配置/代码快照 | 支撑重现和审计 | 新增 0007/API/ADR-038 |
| S6-D02 | 失败仅保存 safe case ID/check code | 防止评测语料复制泄露 | API 不返回原始问答 |
| S6-D03 | 本地同步评测器在 staging/production fail-closed | 避免合成门禁冒充生产 | 生产需外部 Worker |
| S6-D04 | 指标只用路由模板等低基数属性 | 隐私与成本 | 禁止 tenant/user/query 标签 |
| S6-D05 | 使用实例私有 OTel Provider | 测试可重复、无全局污染 | 手工 middleware/生命周期 flush |
| S6-D06 | 单进程快照明确不是 SLO 证据 | 避免语义混用 | Prometheus 才计算跨实例 SLO |
| S6-D07 | 可用性用多窗口燃尽率告警 | 降噪并快速发现严重故障 | 规则带 Owner/Runbook |
| S6-D08 | 压测默认本地并设置硬上限 | 防止误打外部环境和费用失控 | 非本地需显式开关 |
| S6-D09 | 故障注入只使用 Fake Provider | 确定性且无外部影响 | 真实故障仍是生产阻断 |
| S6-D10 | Gate 需要恢复不变量，不接受“备份成功” | 备份不等于可恢复 | 本地/生产分别演练 |
| S6-D11 | Compose Grafana 匿名 Viewer 仅限 localhost | 降低本地学习门槛 | 生产强制企业 SSO/RBAC |
| S6-D12 | 保留 99.9%/2.5s/15s/RPO15m/RTO60m 为未签字假设 | 防止伪造承诺 | 目标环境可经变更流程校准 |

正式 ADR：ADR-038 至 ADR-043。
