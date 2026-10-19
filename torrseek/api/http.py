"""HttpClient: adapter for the real API.

The real contract is not known yet. This implementation follows the
endpoints assumed in the spec, so it can already be exercised against a
local mock server (see tests/mock_server.py). When the real API arrives,
only the request building and the `_to_*` mapping functions below change.

    GET /search?q=&cat=&page=&sort=  -> SearchPage JSON
    GET /torrents/{id}               -> TorrentDetails JSON
    GET /torrents/{id}/file          -> application/x-bittorrent
"""
from __future__ import annotations

import json
import socket
from datetime import datetime
from urllib import error, parse, request

from ..models import FileEntry, SearchPage, Sort, TorrentDetails, TorrentItem
from .base import ApiError, NetworkError, NotFound, RateLimited


class HttpClient:
    def __init__(self, base_url: str, token: str | None = None, *, timeout: float = 15.0):
        if not base_url:
            raise ApiError("base_url is not configured for the http adapter")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout

    def __repr__(self) -> str:  # never leak the token into logs or tracebacks
        return f"HttpClient(base_url={self.base_url!r}, token={'***' if self._token else None})"

    # -- transport ---------------------------------------------------------
    def _get(self, path: str, params: dict | None = None) -> tuple[bytes, str]:
        url = self.base_url + path
        if params:
            url += "?" + parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = request.Request(url, headers={"Accept": "application/json, application/x-bittorrent",
                                            "User-Agent": "TorrSeek/0.1"})
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except error.HTTPError as e:
            if e.code == 404:
                raise NotFound(f"{path} not found") from None
            if e.code == 429:
                try:
                    retry = float(e.headers.get("Retry-After", "5"))
                except ValueError:
                    retry = 5.0
                raise RateLimited(retry_after=retry) from None
            raise ApiError(f"HTTP {e.code}") from None
        except (error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise NetworkError(str(reason)) from None

    def _json(self, path: str, params: dict | None = None) -> dict:
        body, _ = self._get(path, params)
        try:
            return json.loads(body)
        except ValueError:
            raise ApiError("invalid JSON in response") from None

    # -- mapping (the part that changes for the real API) ------------------
    @staticmethod
    def _to_item(d: dict) -> TorrentItem:
        return TorrentItem(
            id=str(d["id"]), title=d["title"], size_bytes=int(d["size_bytes"]),
            seeders=int(d["seeders"]), leechers=int(d["leechers"]),
            category=d.get("category") or "", uploaded_at=datetime.fromisoformat(d["uploaded_at"]),
        )

    def _to_details(self, d: dict) -> TorrentDetails:
        item = self._to_item(d)
        return TorrentDetails(
            **item.__dict__,
            description=d.get("description", ""),
            files=[FileEntry(f["path"], int(f["size_bytes"])) for f in d.get("files", [])],
            infohash=d["infohash"], magnet=d["magnet"],
        )

    # -- SearchClient ------------------------------------------------------
    def search(self, query: str, *, category: str | None = None,
               page: int = 1, sort: Sort = Sort.SEEDERS) -> SearchPage:
        d = self._json("/search", {"q": query, "cat": category, "page": page, "sort": sort.value})
        try:
            return SearchPage(items=[self._to_item(x) for x in d["items"]], page=int(d["page"]),
                              total_pages=int(d["total_pages"]), total_found=int(d["total_found"]))
        except (KeyError, TypeError, ValueError) as e:
            raise ApiError(f"unexpected response: {e}") from None

    def details(self, torrent_id: str) -> TorrentDetails:
        d = self._json(f"/torrents/{parse.quote(torrent_id, safe='')}")
        try:
            return self._to_details(d)
        except (KeyError, TypeError, ValueError) as e:
            raise ApiError(f"unexpected response: {e}") from None

    def download_torrent(self, torrent_id: str) -> bytes:
        body, _ = self._get(f"/torrents/{parse.quote(torrent_id, safe='')}/file")
        return body
