# ADR-041：压测与故障注入工具默认有界且仅面向本地

- 状态：Accepted
- 日期：2026-07-16
- Owner：SRE / QA / Security

## 决策

- `load_s6.py` 默认只允许 localhost，非本地目标必须显式 `--allow-nonlocal`。
- 工具上限为 100 RPS、300 秒、64 并发；令牌从环境或本地 Fake OIDC 获取且不打印。
- `fault_s6.py` 只使用确定性 Fake Provider 注入 429、全路由 429、超时和缺失用量，不连接真实供应商。
- 每份输出都携带 `production_*_evidence=false`，不得把开发机结果写成生产容量结论。

## 后果

开发者可以安全学习和重复韧性验证；目标集群压测仍需变更单、容量预算、监控和停止条件。
