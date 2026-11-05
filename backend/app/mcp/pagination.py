"""Cursor-backed pagination helpers shared by list tools."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.mcp.cursor import CursorCodec

Key = tuple[Any, ...]


def paginate[T](
    items: Sequence[T],
    *,
    limit: int,
    cursor: str | None,
    codec: CursorCodec,
    tenant_id: str,
    tool: str,
    query_hash: str,
    key_fn: Callable[[T], Key],
) -> tuple[list[T], str | None]:
    """Return one page plus the next cursor.

    Records are ordered by ``key_fn`` descending. A cursor stores the last key of
    the previous page, so paging never uses offsets.
    """
    ordered = sorted(items, key=key_fn, reverse=True)
    if cursor:
        payload = codec.decode(cursor, tenant_id=tenant_id, tool=tool, query_hash=query_hash)
        raw_key = payload.get("k")
        after = tuple(raw_key) if isinstance(raw_key, list) else (raw_key,)
        ordered = [item for item in ordered if key_fn(item) < after]
    page = ordered[:limit]
    next_cursor = None
    if len(ordered) > limit and page:
        next_cursor = codec.encode(
            tenant_id=tenant_id,
            tool=tool,
            query_hash=query_hash,
            last_key=list(key_fn(page[-1])),
        )
    return page, next_cursor
