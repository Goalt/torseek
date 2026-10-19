"""The SearchClient contract and its errors.

The UI and the controller depend only on this module; adapters
(mock.py, http.py) implement SearchClient.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import SearchPage, Sort, TorrentDetails


class ApiError(Exception):
    """Base error for anything an adapter can raise."""

    def user_message(self) -> str:
        return f"Ошибка API: {self}" if str(self) else "Ошибка API"


class NotFound(ApiError):
    def user_message(self) -> str:
        return "Раздача не найдена"


class RateLimited(ApiError):
    def __init__(self, retry_after: float = 0, message: str = ""):
        super().__init__(message or f"rate limited, retry after {retry_after:g}s")
        self.retry_after = retry_after

    def user_message(self) -> str:
        return f"Слишком много запросов, подождите {self.retry_after:g} с и нажмите r"


class NetworkError(ApiError):
    def user_message(self) -> str:
        return "Нет связи с сервером, r - повторить"


@runtime_checkable
class SearchClient(Protocol):
    def search(self, query: str, *, category: str | None = None,
               page: int = 1, sort: Sort = Sort.SEEDERS) -> SearchPage: ...

    def details(self, torrent_id: str) -> TorrentDetails: ...

    def download_torrent(self, torrent_id: str) -> bytes: ...
