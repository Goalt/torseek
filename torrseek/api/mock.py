"""MockClient: an offline SearchClient backed by fixtures/torrents.json.

Special queries for tests and UI checks:
    __error__      -> ApiError
    __ratelimit__  -> RateLimited(retry_after=5)
    __empty__      -> empty result
    __network__    -> NetworkError (extra, to check the retry path)
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path

from .. import torrentfile
from ..models import FileEntry, SearchPage, Sort, TorrentDetails, TorrentItem, sort_items
from .base import ApiError, NetworkError, NotFound, RateLimited

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "torrents.json"
PER_PAGE = 20


class MockClient:
    def __init__(self, fixtures: str | Path | None = None, *,
                 delay: tuple[float, float] = (0.2, 0.6), per_page: int = PER_PAGE,
                 seed: int | None = None):
        self._path = Path(fixtures) if fixtures else FIXTURES
        self._records: dict[str, dict] | None = None
        self.delay = delay
        self.per_page = per_page
        self._rng = random.Random(seed)

    # -- helpers -----------------------------------------------------------
    @property
    def records(self) -> dict[str, dict]:
        if self._records is None:  # lazy: keeps cold start fast
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._records = {r["id"]: r for r in data}
        return self._records

    def _sleep(self) -> None:
        lo, hi = self.delay
        if hi > 0:
            time.sleep(self._rng.uniform(lo, hi))

    @staticmethod
    def _item(r: dict) -> TorrentItem:
        return TorrentItem(
            id=r["id"], title=r["title"], size_bytes=r["size_bytes"],
            seeders=r["seeders"], leechers=r["leechers"], category=r["category"],
            uploaded_at=datetime.fromisoformat(r["uploaded_at"]),
        )

    def _record(self, torrent_id: str) -> dict:
        try:
            return self.records[torrent_id]
        except KeyError:
            raise NotFound(f"torrent {torrent_id!r} not found") from None

    # -- SearchClient ------------------------------------------------------
    def search(self, query: str, *, category: str | None = None,
               page: int = 1, sort: Sort = Sort.SEEDERS) -> SearchPage:
        self._sleep()
        q = query.strip()
        if q == "__error__":
            raise ApiError("mock: internal server error (500)")
        if q == "__ratelimit__":
            raise RateLimited(retry_after=5)
        if q == "__network__":
            raise NetworkError("mock: connection reset")
        if page < 1:
            raise ApiError(f"invalid page {page}")
        if q == "__empty__":
            return SearchPage(items=[], page=page, total_pages=0, total_found=0)

        needle = q.casefold()
        found = [
            self._item(r) for r in self.records.values()
            if needle in r["title"].casefold()
            and (category is None or r["category"] == category)
        ]
        found = sort_items(found, sort)
        total_pages = -(-len(found) // self.per_page)
        start = (page - 1) * self.per_page
        return SearchPage(items=found[start:start + self.per_page], page=page,
                          total_pages=total_pages, total_found=len(found))

    def details(self, torrent_id: str) -> TorrentDetails:
        self._sleep()
        r = self._record(torrent_id)
        item = self._item(r)
        return TorrentDetails(
            **item.__dict__,
            description=r["description"],
            files=[FileEntry(f["path"], f["size_bytes"]) for f in r["files"]],
            infohash=r["infohash"],
            magnet=torrentfile.magnet(r["infohash"], r["title"]),
        )

    def download_torrent(self, torrent_id: str) -> bytes:
        self._sleep()
        return torrentfile.build_torrent(self._record(torrent_id))
