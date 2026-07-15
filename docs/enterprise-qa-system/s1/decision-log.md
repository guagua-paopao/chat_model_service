# S1 决策日志

| ID | 日期 | 状态 | 决策 | 理由 | 证据/ADR | 复审触发器 |
|---|---|---|---|---|---|---|
| S1-DEC-001 | 2026-07-15 | accepted | 本地使用独立 Fake IdP 完整覆盖 Code + PKCE/JWKS | 企业 IdP 未提供，但不能跳过协议与浏览器边界 | ADR-009 | 企业 OIDC 注册完成 |
| S1-DEC-002 | 2026-07-15 | accepted | Fake IdP 只进 Compose，不进 Helm/生产 | 防止开发身份源误部署 | ADR-009 | 无；生产不可放宽 |
| S1-DEC-003 | 2026-07-15 | accepted | staging/production 配置层禁止开发 JWT | 配置错误应 fail-fast | ADR-009 | 无；只能加强 |
| S1-DEC-004 | 2026-07-15 | accepted | token 中 tenant_id 只用于可信定位，角色/状态仍查数据库 | 支持禁用和权限实时控制，不信任客户端字段 | ADR-009/010 | 企业 IdP claims 映射评审 |
| S1-DEC-005 | 2026-07-15 | accepted | Repository 公共方法强制 tenant_id；私有会话同时强制 user_id | 将隔离规则变成可测试 API，而非编码习惯 | ADR-010 | 共享会话/服务账号立项 |
| S1-DEC-006 | 2026-07-15 | accepted | 跨租户与不存在资源统一 404 | 降低资源枚举侧信道 | ADR-010 | 安全规范变化 |
| S1-DEC-007 | 2026-07-15 | accepted | UUIDv7 + signed keyset cursor | 并发插入下稳定分页，游标不能跨作用域复用 | ADR-011 | 列表排序/过滤变化 |
| S1-DEC-008 | 2026-07-15 | accepted | PATCH 使用 ETag/If-Match 乐观并发 | 防止静默丢失更新 | ADR-011 | 协同编辑需求出现 |
| S1-DEC-009 | 2026-07-15 | accepted | Next.js BFF 持有 HttpOnly token，并以双提交 CSRF 保护写请求 | 减少浏览器 token 暴露并控制 CSRF | ADR-012 | 企业统一 BFF/网关接入 |
| S1-DEC-010 | 2026-07-15 | accepted | BFF 只代理 me/conversations 白名单 | 避免通用代理/SSRF 与未来接口意外暴露 | ADR-012 | 每新增接口逐项评审 |
| S1-DEC-011 | 2026-07-15 | accepted | Python/npm 锁文件与 SCA/secret/image 门禁进入 CI | 提供可复现和可审计供应链 | ADR-013 | 构建平台升级/SBOM 接入 |
| S1-DEC-012 | 2026-07-15 | accepted | 生产迁移为独立 Job，API 不自动建表 | 避免多副本竞态和不可控 schema 变更 | ADR-001/013 | 迁移平台替代方案评审 |
| S1-DEC-013 | 2026-07-15 | accepted | S1 Gate 采用“条件通过 S2 合成开发” | 核心纵切已验证，但企业 IdP、远端 dev 部署和集群未验证 | S1 Gate | 三项企业集成证据完成 |
| S1-DEC-014 | 2026-07-15 | accepted | Compose 数据库种子按依赖顺序分批 flush | PostgreSQL 外键不会依赖 ORM 偶然插入顺序 | 测试报告 | 种子机制替换 |

改变已接受决策时追加记录或使用新 ADR supersede；不得删除历史。S0 的业务、数据、模型和安全约束继续有效。

