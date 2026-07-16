# ADR-048：灰度事件哈希链

状态：Accepted（2026-07-16）。

## 决策

每个候选的 start/advance/stop/rollback/completed 事件按序追加，并以 `previous_hash + 规范化事件` 生成 SHA-256；API 返回链完整性结果。

## 理由与后果

这能发现数据库内的删除、改序和篡改，但不能抵抗有权重写整条链的攻击者。生产仍需将锚点外送 WORM/SIEM。
