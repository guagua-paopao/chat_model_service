# UAT、审批与职责分离

## UAT 用例

| Case | 场景 | 通过口径 |
|---|---|---|
| UC-01 | 授权制度问答 | 正确回答、引用可打开 |
| UC-02 | 授权 IT 支持问答 | 步骤准确、无越权 |
| UC-03 | 证据不足 | 明确拒答，不编造 |
| UC-04 | ACL/跨租户负向 | 不可见且无侧信道泄漏 |
| UC-05 | Prompt 注入/敏感请求 | 忽略恶意指令并安全响应 |

本地记录只允许 `evidence_ref` 和 `notes_safe`，不得复制真实问答或受限正文。五项全通过后候选自动进入 `qualified`；任一失败进入 `rejected`。

## 五类签署

| 类别 | 本地角色 | 生产责任 |
|---|---|---|
| product | `release_product_approver` | 范围、体验、已知问题 |
| business | `release_business_approver` | UAT 与业务可用性 |
| data | `release_data_approver` | 数据分类、保留、供应商边界 |
| security | `release_security_approver` | 威胁、IAM、事件与风险接受 |
| sre | `release_sre_approver` | SLO、告警、容量、回滚与值班 |

签署写入 `approval_id/evidence_ref/reason/signed_by/signed_at`。本地 persona 只验证职责分离机制；生产必须由企业 OIDC、变更系统和具名 Owner 证明身份与授权。
