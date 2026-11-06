# search 公开契约

**模块**: M11 search | **Owner**: agent-search

```python
@dataclass(frozen=True)
class SearchHit:
    badcase_id: str
    dataset_id: str | None
    sample_id: str | None
    score: float | None

@dataclass(frozen=True)
class BadcaseSearchResult:
    hits: list[SearchHit]
    degraded: bool = False

class SemanticSearch(Protocol):
    def search_badcases(self, *, tenant_id: str, query: str | None,
                        dataset_id: str | None, tags: tuple[str, ...],
                        limit: int) -> BadcaseSearchResult: ...
```

## 规则

1. 查询强制 `tenant_id`；跨租户结果恒为空。
2. top-k 默认 10，最大 50；返回 score。
3. payload 只存引用 ID，不存完整 Prompt/样本正文。
4. Qdrant 超时/不可用 → MySQL 关键词检索，`degraded=true`，不返回 5xx；P95 ≤1s。
5. Embedding 版本可切换、可重建；索引失败可重试。
