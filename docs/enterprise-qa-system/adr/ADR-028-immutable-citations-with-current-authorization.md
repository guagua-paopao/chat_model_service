# ADR-028：引用快照不可变，查看时按当前权限再鉴权

- 状态：Accepted
- 日期：2026-07-16

## 背景

审计要求知道历史回答当时引用的版本和原句；撤权要求用户不能继续通过旧链接读取内容。让 citation 自动漂移到 current version 会破坏历史证据，让永久 URL 继续可见会绕过撤权。

## 决策

Citation 保存本次 hit、document/version/chunk、title/page/section/quote/score 的不可变快照。详情请求重新验证消息归属、tenant、文档未删除和当前 user/role read ACL；返回长度受限 preview，`source_url=null`。

## 后果

兼顾可追踪和即时撤权；需要明确 citation 快照的保留、法律删除与加密策略。旧 version 可作为历史依据，不进入新检索。
