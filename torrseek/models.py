"""Data models shared by the UI, the controller and every API adapter."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class Sort(enum.Enum):
    SEEDERS = "seeders"
    SIZE = "size"
    DATE = "date"

    @property
    def label(self) -> str:
        return {"seeders": "сиды", "size": "размер", "date": "дата"}[self.value]

    def next(self) -> "Sort":
        order = list(Sort)
        return order[(order.index(self) + 1) % len(order)]


# Categories used by the mock. The real API may define its own list;
# config.toml can override it with `categories = [...]`.
DEFAULT_CATEGORIES = ("linux", "software", "video", "audio", "books", "dataset")


@dataclass(frozen=True)
class TorrentItem:
    id: str
    title: str
    size_bytes: int
    seeders: int
    leechers: int
    category: str
    uploaded_at: datetime


@dataclass(frozen=True)
class SearchPage:
    items: list[TorrentItem]
    page: int
    total_pages: int
    total_found: int


@dataclass(frozen=True)
class FileEntry:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class TorrentDetails(TorrentItem):
    description: str = ""
    files: list[FileEntry] = field(default_factory=list)
    infohash: str = ""
    magnet: str = ""

    def as_item(self) -> TorrentItem:
        return TorrentItem(self.id, self.title, self.size_bytes, self.seeders,
                           self.leechers, self.category, self.uploaded_at)


def sort_items(items: list[TorrentItem], sort: Sort) -> list[TorrentItem]:
    """Descending sort used by the mock and by local re-sorting in the UI."""
    if sort is Sort.SIZE:
        key = lambda t: (t.size_bytes, t.seeders)
    elif sort is Sort.DATE:
        key = lambda t: (t.uploaded_at, t.seeders)
    else:
        key = lambda t: (t.seeders, t.size_bytes)
    return sorted(items, key=key, reverse=True)


def human_size(n: int) -> str:
    """Compact size, at most 6 characters: '512B', '1.4K', '700M', '4.7G'."""
    units = "BKMGTP"
    value = float(n)
    i = 0
    while value >= 1000 and i < len(units) - 1:
        value /= 1024
        i += 1
    if i == 0:
        return f"{int(value)}B"
    if value < 10:
        return f"{value:.1f}{units[i]}"
    return f"{int(round(value))}{units[i]}"


def parse_size(text: str) -> int | None:
    """Parse '700M', '1.5g', '2GB', '500' (bare number = megabytes).

    Returns None for empty input, raises ValueError on garbage.
    """
    s = text.strip().upper().removesuffix("B")
    if not s:
        return None
    mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    unit = s[-1]
    if unit in mult:
        number = s[:-1]
    else:
        unit, number = "M", s
    value = float(number)
    if value < 0:
        raise ValueError(text)
    return int(value * mult[unit])
