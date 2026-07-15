# S0 阶段基线包

> 阶段：发现、样本与技术基线  
> 版本：s0-v1.0  
> 日期：2026-07-15  
> Gate：条件通过（工程准备完成，真实业务/模型证据待补）

## 1. S0 目标

将“做一个问答系统”转为可验证、可追踪的企业项目定义，冻结首发场景、安全边界、质量门槛和首批技术决策，并准备可自动执行的评测样本。

## 2. S0 产物

| 产物 | 文件 | 状态 |
|---|---|---|
| 业务发现与范围基线 | [01-discovery-baseline.md](01-discovery-baseline.md) | 工程基线完成，业务签字待补 |
| 数据清单与治理 | [02-data-inventory.md](02-data-inventory.md) | 合成清单完成，真实数据待盘点 |
| 黄金集说明 | [03-golden-dataset.md](03-golden-dataset.md) | 60 条合成样例完成 |
| 裸模型/RAG 实验 | [04-baseline-experiment.md](04-baseline-experiment.md) | 协议完成，真实模型运行待凭证 |
| 威胁模型 v0.1 | [05-threat-model.md](05-threat-model.md) | 完成 |
| 容量与成本基线 | [06-capacity-and-cost-baseline.md](06-capacity-and-cost-baseline.md) | 三档情景完成，价格待确认 |
| 风险登记册 | [07-risk-register.md](07-risk-register.md) | 完成 |
| 开放问题与决策请求 | [08-open-questions.md](08-open-questions.md) | 待业务输入 |
| S0 Gate 记录 | [09-s0-gate-review.md](09-s0-gate-review.md) | 条件通过 |
| 决策日志 | [decision-log.md](decision-log.md) | 完成 |
| 机器可读清单 | [manifest.yaml](manifest.yaml) | 完成 |
| ADR | [../adr](../adr/) | ADR-001～008 已接受 |
| 合成知识语料 | [../../../tests/fixtures/knowledge](../../../tests/fixtures/knowledge/) | 6 份当前/历史/受限/恶意样本 |
| 黄金数据 | [../../../tests/evaluation/s0-golden-dataset.jsonl](../../../tests/evaluation/s0-golden-dataset.jsonl) | 60 条，schema v1 |

## 3. 已冻结范围

- 首发用户：企业内部员工、知识管理员、租户管理员和审计员。
- 首发业务：员工制度问答、IT 支持问答。
- 首发渠道：Web 与受控 REST API。
- 交互：只读、带引用、可拒答；不执行工具写操作。
- 数据：合成数据可用于 S0/S1；真实数据必须完成分类、授权、脱敏和 ACL 映射后进入 test/staging。

## 4. 如何继续

S1 开始前至少确认开放问题 OQ-001～OQ-005；若尚未确认，可使用合成租户和 Fake Provider 开发，但不得对生产数据、成本或业务收益作承诺。

每次改变首发场景、数据外发、技术栈、租户隔离、文档版本、协议或评测门禁时，先更新对应 ADR、`decision-log.md` 与根目录 `PROJECT_CONTEXT.md`。
