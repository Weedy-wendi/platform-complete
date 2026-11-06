# catalog 公开契约

**模块**: M04 catalog | **Owner**: agent-data

## DTO / 协议

```python
@dataclass(frozen=True)
class DatasetVersionRef:
    tenant_id: str
    dataset_id: str
    version: int
    content_hash: str

@dataclass(frozen=True)
class CatalogReader(Protocol):
    def list_projects(self, ctx: TenantContext, cursor: str | None, limit: int) -> Page[ProjectView]: ...
    def search_datasets(self, ctx: TenantContext, query: DatasetQuery) -> Page[DatasetView]: ...
    def get_version(self, ctx: TenantContext, ref: DatasetVersionRef) -> DatasetVersionView: ...
    def page_samples(self, ctx: TenantContext, ref: DatasetVersionRef, cursor: str | None, limit: int) -> Page[SampleView]: ...
```

## 不变量

1. `dataset_version` 发布后不可 UPDATE；只能新建版本。
2. `content_hash` 由样本规范化内容计算；同内容重复发布返回已有版本。
3. 版本号在数据集内单调递增、无空洞。
4. `(dataset_version_id, sample_key)` 去重；`row_count` 与实际行数一致。
5. 所有查询强制 `tenant_id`；跨租户 NotFound。
6. 大 payload >1MB 走 `artifact` 引用。

## 事件

`catalog.dataset.version_published`、`catalog.sample.batch_ingested`。
