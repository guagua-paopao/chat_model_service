# ADR-007：Prompt、检索和模型路由版本化发布

- Status：Accepted
- Decision date：2026-07-15
- Owners：AI / Product / Platform
- Review date：S4 配置中心实现后

## Context

Prompt、top-k、阈值、reranker 和模型路由会直接改变答案、成本与安全。如果以环境变量或可变数据库行直接覆盖，就无法复现历史回答、比较候选或快速回滚。

## Decision

配置采用逻辑对象 + 不可变版本，状态为 draft/approved/published/retired。候选版本通过固定评测和审批后原子发布；消息、检索运行和 release manifest 保存版本 ID。灰度按稳定分桶，不能在同一会话中无记录切换。

## Alternatives

- 环境变量：适合进程配置，不适合需审批/回滚的业务策略。
- 直接编辑当前行：简单但历史和审计丢失。
- Prompt 仅保存在代码：可版本化但业务发布、灰度和快速回滚不便。

## Consequences

需要配置 schema、审批 UI/流程和版本存储；换来复现、A/B、审计和回滚。配置版本与代码兼容性必须在发布时验证。

## Security and Cost

系统 Prompt 对普通角色可以受控，但不能被当成唯一秘密边界。路由版本保存数据政策和价格快照；高成本或外部路由变更需相应批准。

