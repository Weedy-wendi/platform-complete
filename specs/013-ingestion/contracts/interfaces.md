# ingestion 公开契约

**模块**: M05 ingestion | **Owner**: agent-data

```python
@dataclass(frozen=True)
class ConnectorCursor:
    value: str | None
    updated_at: datetime | None

class Connector(Protocol):
    def discover(self) -> list[ConnectorField]: ...
    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict], ConnectorCursor]: ...

@dataclass(frozen=True)
class SyncResult:
    job_id: str
    rows_read: int
    rows_written: int
    rows_skipped: int
    next_cursor: ConnectorCursor
```

## 规则

1. 水位只在批次成功后推进。
2. 幂等键防重复样本；失败入 DLQ，可重放。
3. 取消在 5 秒内生效。
4. Schema 漂移记录并告警；清洗规则可预览。
5. 大文件流式读取；编码错误明确报错。
