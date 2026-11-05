# Tasks: audit（M02）

**Source of truth**: `docs/planning/task-index.md`；明细见 `docs/planning/tasks/00-foundation.md`。

- [X] AUD-01 `audit_log` 表与写入器
- [X] AUD-02 append-only 与保留策略（180 天、分区）
- [X] AUD-03 审计查询接口（租户隔离、分页、只读）

## 交付检查

- [X] 无 UPDATE/DELETE 授权
- [X] 分区可预建/删除
- [X] 审计写入失败不阻塞主请求
- [X] 查询跨租户 0 行
