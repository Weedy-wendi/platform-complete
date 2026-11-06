# Tasks: search（M11）

**Source of truth**: `docs/planning/task-index.md`；明细见 `docs/planning/tasks/01-data.md`。

- [X] SRC-01 VectorIndex SPI
- [X] SRC-02 Qdrant 适配
- [X] SRC-03 Embedding 版本管理
- [X] SRC-04 索引任务与重建
- [X] SRC-05 语义检索 + 关键词降级
- [X] SRC-06 租户隔离与降级测试

## 交付检查

- [X] 跨租户 0 结果
- [X] Qdrant 故障时 `degraded=true`
- [X] payload 不含正文/PII
- [X] 降级 P95 ≤1s
