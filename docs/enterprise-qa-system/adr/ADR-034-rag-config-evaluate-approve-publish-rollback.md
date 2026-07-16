# ADR-034：RAG 配置必须经过评测、独立审批、发布与不可变回滚

- 状态：Accepted
- 日期：2026-07-16
- Owner：AI Quality / Knowledge / Security

## 背景

ADR-026 已要求配置不可变，但 S4 自动创建首个 published 配置，缺少候选评测、职责分离、审批证据和安全回滚。

## 决策

配置状态机固定为 `draft → evaluated → approved → published → archived`：

- Draft 包含完整 Prompt、检索参数、原因、创建人、版本与 checksum，创建后不原地改写。
- 评测由服务端选择 evaluator 与 dataset 版本，客户端不能提交“通过”结果。
- 只有 passing evaluation 可审批；创建人不得审批自己的版本。
- 发布必须引用独立审批号，事务内归档旧版本并发布新版本。
- 回滚不是重新激活旧行，而是创建 checksum 相同、version 更高且 `rollback_of_id` 指向历史版本的新 published 行。
- local evaluator 只验证结构、安全边界和阈值，staging/production 启动配置禁止它；生产必须接入批准数据集和外部评测 Worker。

## 后果

配置历史可解释、可回滚，职责分离可自动测试。S5 本地 passing 不能代替真实黄金集、holdout、红队和业务 Owner 签字；在外部评测 Worker 完成前配置生产发布仍为 No-Go。

