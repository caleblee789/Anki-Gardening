from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Generic, TypeVar


Key = TypeVar("Key")
Value = TypeVar("Value")


class BoundedLruCache(Generic[Key, Value]):
    """Small deterministic LRU used by per-widget render caches.

    Qt image objects should remain owned by the GUI-thread widget that created
    them, so this deliberately avoids a process-global cache.  The narrow API
    also makes every cache insertion pass through the same hard size bound.
    """

    def __init__(
        self, max_entries: int, *, max_bytes: int | None = None,
        size_of: Callable[[Value], int] | None = None,
    ) -> None:
        if max_bytes is not None and size_of is None:
            raise ValueError("A byte-bounded cache requires size_of")
        self.max_entries = max(1, int(max_entries))
        self.max_bytes = None if max_bytes is None else max(0, int(max_bytes))
        self._size_of = size_of
        self._items: OrderedDict[Key, Value] = OrderedDict()
        self._sizes: dict[Key, int] = {}
        self.current_bytes = 0

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: Key, default: Value | None = None) -> Value | None:
        try:
            value = self._items.pop(key)
        except KeyError:
            return default
        self._items[key] = value
        return value

    def __setitem__(self, key: Key, value: Value) -> None:
        size = max(0, int(self._size_of(value))) if self._size_of else 0
        self._items.pop(key, None)
        self.current_bytes -= self._sizes.pop(key, 0)
        # A single oversize image is usable by its caller but must not evict
        # the whole working set or exceed this cache's memory budget.
        if self.max_bytes is not None and size > self.max_bytes:
            return
        self._items[key] = value
        self._sizes[key] = size
        self.current_bytes += size
        while len(self._items) > self.max_entries or (
            self.max_bytes is not None and self.current_bytes > self.max_bytes
        ):
            evicted, _value = self._items.popitem(last=False)
            self.current_bytes -= self._sizes.pop(evicted)

    def clear(self) -> None:
        self._items.clear()
        self._sizes.clear()
        self.current_bytes = 0


def pixmap_bytes(pixmap: object) -> int:
    """Estimate decoded Qt storage in physical pixels, including high DPI."""
    return int(pixmap.width()) * int(pixmap.height()) * ((int(pixmap.depth()) + 7) // 8)
