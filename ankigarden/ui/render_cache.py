from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar


Key = TypeVar("Key")
Value = TypeVar("Value")


class BoundedLruCache(Generic[Key, Value]):
    """Small deterministic LRU used by per-widget render caches.

    Qt image objects should remain owned by the GUI-thread widget that created
    them, so this deliberately avoids a process-global cache.  The narrow API
    also makes every cache insertion pass through the same hard size bound.
    """

    def __init__(self, max_entries: int) -> None:
        self.max_entries = max(1, int(max_entries))
        self._items: OrderedDict[Key, Value] = OrderedDict()

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
        self._items.pop(key, None)
        self._items[key] = value
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
