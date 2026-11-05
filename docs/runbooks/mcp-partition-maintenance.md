# MCP 审计分区维护

`mcp_tool_call` 按 `created_at` 做 RANGE COLUMNS 分区。迁移只预建最近两个月和
`pmax`；本运行手册用于每月预建未来分区并删除 90 天前的分区。

## 权限

使用具备 `ALTER` 权限的管理账号（root / DBA），**不要**使用 MCP 运行时账号：

- `pingce_mcp_ro`：仅 `SELECT`
- `pingce_mcp_audit`：仅 `INSERT mcp_tool_call`

## 每月执行

```powershell
cd backend
$env:PINGCE_MAINT_DSN = "mysql+pymysql://root:<password>@127.0.0.1:3306/pingce?charset=utf8mb4"
pingce mcp maintain-partitions --dsn $env:PINGCE_MAINT_DSN --months-ahead 3 --retention-days 90 --dry-run
pingce mcp maintain-partitions --dsn $env:PINGCE_MAINT_DSN --months-ahead 3 --retention-days 90
```

先 `--dry-run` 确认 `create` / `drop` 列表，再去掉该参数执行。

## 行为

- 预建未来 `months_ahead` 个月的分区（默认 3 个月）。
- 删除「月末早于 `today - retention_days`」的分区（默认 90 天）。
- 保留 `pmax` 作为兜底分区。
- 通过 `information_schema.PARTITIONS` 判断已存在分区，重复执行幂等。

## 调度建议

- 每月 1 日 02:00（UTC）执行一次。
- 任务失败需告警；`pmax` 持续增长通常意味着维护任务未执行。
- 删除分区前确认备份/归档策略满足合规要求。

## 回滚

分区维护只做 `ADD`/`DROP PARTITION`，不修改行数据。误删分区无法回滚，必须在
执行前确认 `--dry-run` 输出与保留策略一致。
