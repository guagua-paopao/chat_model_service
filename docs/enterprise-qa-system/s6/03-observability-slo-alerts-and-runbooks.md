# 可观测性、SLI/SLO、告警与 Runbook

## 1. 遥测拓扑

API 使用 OTel SDK 1.43.0 发送 OTLP gRPC；Collector 接收 Trace/Metric，Trace 本地输出 debug，Metric 以 Prometheus exporter 暴露；Prometheus 3.10.0 抓取，Grafana 13.1.0 预置只读仪表盘。

允许的指标标签：`http_request_method`、`http_route`、`http_response_status_code`、`qa_evaluation_gate_result`。禁止 tenant/user/query/prompt/document/UUID。

核心指标：

- `enterprise_qa_qa_http_requests_total`
- `enterprise_qa_qa_http_request_duration_seconds_bucket`
- `enterprise_qa_qa_evaluation_runs_total`
- `enterprise_qa_qa_evaluation_quality_score_bucket`

## 2. SLI/SLO

| SLI | PromQL 要点 | 目标/说明 |
|---|---|---|
| 可用性 | `1 - 5xx / all` | 99.9% 假设基线 |
| API P95 | request duration histogram | 2.5 s 诊断阈值 |
| TTFT P95 | 首个 SSE 数据时间 | 真实 Provider 接入后单独上报 |
| 评测失败 | failed gate increase | 任一 release gate 立即阻断 |
| 遥测完整性 | `up`/`absent` | 5 分钟缺失触发 P1 |

`/admin/operations/snapshot` 是单实例、最多 5000 样本的最近 5 分钟窗口，不是 SLO 数据源。

## 3. Dashboard

预置 `Enterprise QA S6 - Quality and Reliability`：可用性、API P95、按状态请求率、评测质量分、评测门禁五个面板。生产需增加 Provider/route、队列年龄、对象存储、数据库连接池、SSE active/TTFT、成本预算和多区域视图，但仍须保持低基数。

## 4. Runbooks

### TelemetryMissing

1. 确认 Prometheus target 与 Collector 容器/Pod 状态。
2. 检查 API 到 Collector 的 DNS、NetworkPolicy、端口和证书。
3. 若业务健康但遥测中断，冻结高风险发布并创建 P1；不要因导出失败重启全部业务副本。
4. 恢复后确认时间序列重新增长、缺口已标注并复盘。

### AvailabilityBurnFast

1. 按 `http_route/status` 查找 5xx 集中路径，再关联 request/trace ID。
2. 检查数据库、Provider、对象存储、队列和最近发布。
3. 优先停发布、切换批准 fallback、降载或回滚不可变配置；不得绕过 ACL/引用门禁。
4. 记录开始/发现/缓解/恢复时间和错误预算消耗。

### ApiLatencyP95High

1. 分离 API、检索、Provider、SSE TTFT 和完整回答耗时。
2. 检查并发/配额锁、连接池、队列年龄、Provider 429/超时。
3. 使用负载削峰或批准的路由回退；不以降低安全阈值换取延迟。
4. 持续 10 分钟恢复后关闭，保存容量与根因证据。

### EvaluationGateFailed

1. 获取 run ID、dataset checksum、候选 checksum、failed case IDs 和 baseline delta。
2. 禁止发布该候选；确认没有误用旧数据集或代码修订。
3. 修正配置/代码后创建新 run，不修改历史记录。
4. 只有数据集问题才走双人复核的新版本流程，禁止直接篡改阈值。

## 5. 生产待办

Alertmanager/Pager 路由、企业 Grafana SSO、Trace 后端、日志集中化、30 天以上保留、告警触发/静默/恢复演练和 named on-call 尚未完成。
