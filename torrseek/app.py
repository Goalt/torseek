"""Controller and state. Knows about SearchClient, nothing about curses.

Keys arrive as normalized names ("UP", "ENTER", "ESC", ...) or single
characters, so the whole flow can be tested without a terminal.
"""
from __future__ import annotations

import enum
import queue
import re
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .api.base import ApiError, SearchClient
from .config import Config, config_dir
from .models import SearchPage, Sort, TorrentDetails, TorrentItem, human_size, parse_size, sort_items

HISTORY_SIZE = 10
SPINNER = "|/-\\"
SPINNER_FPS = 4


class Screen(enum.Enum):
    SEARCH = "search"
    RESULTS = "results"
    DETAILS = "details"


# ---------------------------------------------------------------- runners
class ThreadRunner:
    """Runs blocking client calls in a daemon thread; results are picked up
    by drain() on the UI thread, so all state changes happen there."""

    def __init__(self):
        self._done: queue.Queue = queue.Queue()

    def submit(self, fn: Callable[[], object], callback: Callable[[object, BaseException | None], None]):
        def work():
            try:
                res, exc = fn(), None
            except BaseException as e:  # delivered to the UI thread, never raised there
                res, exc = None, e
            self._done.put((callback, res, exc))

        threading.Thread(target=work, daemon=True).start()

    def drain(self) -> bool:
        changed = False
        while True:
            try:
                cb, res, exc = self._done.get_nowait()
            except queue.Empty:
                return changed
            cb(res, exc)
            changed = True


class SyncRunner:
    """Runs calls immediately (tests, scripted checks)."""

    def submit(self, fn, callback):
        try:
            res, exc = fn(), None
        except BaseException as e:
            res, exc = None, e
        callback(res, exc)

    def drain(self) -> bool:
        return False


# ---------------------------------------------------------------- filter
@dataclass
class Filter:
    category: str | None = None
    min_seeders: int = 0
    min_size: int | None = None
    max_size: int | None = None

    @property
    def active(self) -> bool:
        return bool(self.category or self.min_seeders or self.min_size or self.max_size)

    def match(self, t: TorrentItem) -> bool:
        if self.category and t.category != self.category:
            return False
        if t.seeders < self.min_seeders:
            return False
        if self.min_size is not None and t.size_bytes < self.min_size:
            return False
        if self.max_size is not None and t.size_bytes > self.max_size:
            return False
        return True

    def describe(self) -> str:
        parts = []
        if self.category:
            parts.append(self.category)
        if self.min_seeders:
            parts.append(f"S>={self.min_seeders}")
        if self.min_size is not None:
            parts.append(f">={human_size(self.min_size)}")
        if self.max_size is not None:
            parts.append(f"<={human_size(self.max_size)}")
        return " ".join(parts)


class FilterForm:
    FIELDS = ("category", "min_seeders", "min_size", "max_size")
    LABELS = {"category": "Категория", "min_seeders": "Мин. сидов",
              "min_size": "Размер от", "max_size": "Размер до"}
    ALLOWED = {"min_seeders": "0123456789", "min_size": "0123456789.kmgtbKMGTB",
               "max_size": "0123456789.kmgtbKMGTB"}

    def __init__(self, current: Filter, categories: tuple[str, ...]):
        self.categories = (None,) + tuple(categories)
        self.cat_index = self.categories.index(current.category) if current.category in self.categories else 0
        self.text = {
            "min_seeders": str(current.min_seeders) if current.min_seeders else "",
            "min_size": _size_text(current.min_size),
            "max_size": _size_text(current.max_size),
        }
        self.focus = 0
        self.error = ""

    @property
    def field(self) -> str:
        return self.FIELDS[self.focus]

    def value_text(self, name: str) -> str:
        if name == "category":
            return self.categories[self.cat_index] or "все"
        return self.text[name]

    def reset(self) -> None:
        self.cat_index = 0
        self.text = {k: "" for k in self.text}
        self.error = ""

    def build(self) -> Filter:
        try:
            lo = parse_size(self.text["min_size"])
            hi = parse_size(self.text["max_size"])
        except ValueError:
            raise ValueError("Размер: число и K/M/G/T, например 700M или 1.5G") from None
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("'Размер от' больше чем 'Размер до'")
        return Filter(category=self.categories[self.cat_index],
                      min_seeders=int(self.text["min_seeders"] or 0), min_size=lo, max_size=hi)


def _size_text(n: int | None) -> str:
    return "" if n is None else human_size(n)


# ---------------------------------------------------------------- app
class App:
    def __init__(self, client: SearchClient, cfg: Config | None = None, *,
                 runner=None, history: list[str] | None = None,
                 clock: Callable[[], float] = time.monotonic, persist: bool = True):
        self.client = client
        self.cfg = cfg or Config()
        self.runner = runner or ThreadRunner()
        self.clock = clock
        self.persist = persist
        self.categories = self.cfg.categories

        self.screen = Screen.SEARCH
        # search screen
        self.input = ""
        self.cursor = 0
        self.draft = ""
        self.history = history if history is not None else self._load_history()
        self.hist_sel: int | None = None
        self.cat_index = 0  # 0 = all categories
        # results
        self.query = ""
        self.query_category: str | None = None
        self.sort = Sort.SEEDERS
        self.page: SearchPage | None = None
        self.view: list[TorrentItem] = []
        self.selected = 0
        self.results_top = 0  # first visible row, maintained by the renderer
        self.filter = Filter()
        self.form: FilterForm | None = None
        # details
        self.details: TorrentDetails | None = None
        self.details_scroll = 0
        # status line
        self.status = ""
        self.status_error = False
        self.loading = False
        self.loading_label = ""
        self._loading_since = 0.0
        self._seq = 0
        self._retry: tuple | None = None
        # side effects for the terminal layer, e.g. ("magnet", text)
        self.effects: list[tuple[str, str]] = []

    # ----------------------------------------------------------- helpers
    @property
    def search_category(self) -> str | None:
        return None if self.cat_index == 0 else self.categories[self.cat_index - 1]

    @property
    def request_timeout(self) -> float:
        return self.cfg.timeout + 5

    def spinner_frame(self) -> str:
        if not self.loading:
            return ""
        step = int((self.clock() - self._loading_since) * SPINNER_FPS)
        return SPINNER[step % len(SPINNER)]

    def set_status(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error

    def _load_history(self) -> list[str]:
        try:
            lines = self.cfg.history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        return [x for x in lines if x.strip()][:HISTORY_SIZE]

    def _remember(self, q: str) -> None:
        self.history = [q] + [h for h in self.history if h != q]
        del self.history[HISTORY_SIZE:]
        if not self.persist:
            return
        try:
            self.cfg.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.cfg.history_file.write_text("\n".join(self.history) + "\n", encoding="utf-8")
        except OSError:
            pass  # history is a convenience, never a reason to fail

    def _rebuild_view(self) -> None:
        keep = self.view[self.selected].id if self.view and self.selected < len(self.view) else None
        items = self.page.items if self.page else []
        self.view = sort_items([t for t in items if self.filter.match(t)], self.sort)
        ids = [t.id for t in self.view]
        self.selected = ids.index(keep) if keep in ids else 0

    # ----------------------------------------------------------- requests
    def _request(self, label: str, fn: Callable[[], object], on_ok: Callable[[object], None]) -> None:
        self._seq += 1
        seq = self._seq
        self._retry = (label, fn, on_ok)
        self.loading, self.loading_label = True, label
        self._loading_since = self.clock()
        self.set_status("")

        def done(result, exc):
            if seq != self._seq:
                return  # cancelled or superseded
            self.loading = False
            if exc is None:
                self._retry = None
                on_ok(result)
            elif isinstance(exc, ApiError):
                self.set_status(exc.user_message(), error=True)
            else:
                _log_exception(exc)
                self.set_status(f"Внутренняя ошибка: {type(exc).__name__}: {exc}"[:200], error=True)

        self.runner.submit(fn, done)

    def poll(self) -> bool:
        """Collect finished requests and enforce the request timeout."""
        changed = self.runner.drain()
        if self.loading and self.clock() - self._loading_since > self.request_timeout:
            self._seq += 1
            self.loading = False
            self.set_status("Превышено время ожидания, r - повторить", error=True)
            changed = True
        return changed

    def retry(self) -> None:
        if self.loading:
            return
        if self._retry is None:
            self.set_status("Нечего повторять")
            return
        self._request(*self._retry)

    def cancel(self) -> None:
        self._seq += 1
        self.loading = False
        self.set_status("Запрос отменён")

    def submit_search(self, query: str) -> None:
        q = query.strip()
        if not q:
            self.set_status("Введите запрос", error=True)
            return
        self._remember(q)
        cat = self.search_category
        self._fetch_page(q, cat, 1, new_query=True)

    def _fetch_page(self, q: str, cat: str | None, page: int, new_query: bool = False) -> None:
        sort = self.sort

        def ok(res: SearchPage):
            self.query, self.query_category = q, cat
            self.page = res
            self.view = []
            self.selected = 0
            self.results_top = 0
            self._rebuild_view()
            self.screen = Screen.RESULTS
            if res.total_found == 0:
                self.set_status("Ничего не найдено")
            elif not self.view:
                self.set_status("На странице нет раздач под фильтр (f)")

        label = "Поиск" if new_query else f"Страница {page}"
        self._request(label, lambda: self.client.search(q, category=cat, page=page, sort=sort), ok)

    def open_details(self) -> None:
        if not self.view:
            return
        item = self.view[self.selected]

        def ok(d: TorrentDetails):
            self.details = d
            self.details_scroll = 0
            self.screen = Screen.DETAILS

        self._request("Загрузка карточки", lambda: self.client.details(item.id), ok)

    def download(self) -> None:
        d = self.details
        if d is None:
            return
        target_dir = self.cfg.download_dir

        def work() -> Path:
            data = self.client.download_torrent(d.id)
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                path = target_dir / (safe_filename(d.title) + ".torrent")
                path.write_bytes(data)
            except OSError as e:
                raise ApiError(f"не удалось сохранить файл: {e.strerror or e}") from None
            return path

        def ok(path: Path):
            self.set_status(f"Сохранено: {_short_path(path)}")

        self._request("Скачивание .torrent", work, ok)

    def show_magnet(self) -> None:
        if self.details is None:
            return
        self.effects.append(("magnet", self.details.magnet))
        self.set_status("Magnet скопирован (OSC 52) и выведен в терминал")

    # ----------------------------------------------------------- keys
    def handle_key(self, key: str) -> bool:
        """Process one key. Returns False when the app should exit."""
        if self.form is not None:
            self._key_form(key)
            return True
        if key == "ESC" and self.loading:
            self.cancel()
            return True
        if self.screen is Screen.SEARCH:
            return self._key_search(key)
        if self.screen is Screen.RESULTS:
            return self._key_results(key)
        return self._key_details(key)

    def _key_search(self, key: str) -> bool:
        if key == "ENTER":
            self.submit_search(self.input)
        elif key == "ESC":
            if self.input:  # first Esc clears the line, second one exits
                self._set_input("")
                self.hist_sel = None
            else:
                return False
        elif key == "TAB":
            self.cat_index = (self.cat_index + 1) % (len(self.categories) + 1)
        elif key == "BTAB":
            self.cat_index = (self.cat_index - 1) % (len(self.categories) + 1)
        elif key == "DOWN":
            if self.history:
                if self.hist_sel is None:
                    self.draft = self.input
                    self.hist_sel = 0
                else:
                    self.hist_sel = min(self.hist_sel + 1, len(self.history) - 1)
                self._set_input(self.history[self.hist_sel])
        elif key == "UP":
            if self.hist_sel is not None:
                if self.hist_sel == 0:
                    self.hist_sel = None
                    self._set_input(self.draft)
                else:
                    self.hist_sel -= 1
                    self._set_input(self.history[self.hist_sel])
        elif key == "LEFT":
            self.cursor = max(0, self.cursor - 1)
        elif key == "RIGHT":
            self.cursor = min(len(self.input), self.cursor + 1)
        elif key in ("HOME", "\x01"):
            self.cursor = 0
        elif key in ("END", "\x05"):
            self.cursor = len(self.input)
        elif key == "BACKSPACE":
            if self.cursor:
                self.input = self.input[:self.cursor - 1] + self.input[self.cursor:]
                self.cursor -= 1
                self.hist_sel = None
        elif key == "DELETE":
            self.input = self.input[:self.cursor] + self.input[self.cursor + 1:]
            self.hist_sel = None
        elif key == "\x15":  # Ctrl-U
            self._set_input("")
            self.hist_sel = None
        elif len(key) == 1 and key.isprintable():
            self.input = self.input[:self.cursor] + key + self.input[self.cursor:]
            self.cursor += 1
            self.hist_sel = None
        return True

    def _set_input(self, text: str) -> None:
        self.input = text
        self.cursor = len(text)

    def _go_search(self) -> None:
        self.screen = Screen.SEARCH
        self.hist_sel = None
        self._set_input("")

    def _key_results(self, key: str) -> bool:
        n = len(self.view)
        if key in ("DOWN", "j"):
            self.selected = min(self.selected + 1, max(n - 1, 0))
        elif key in ("UP", "k"):
            self.selected = max(self.selected - 1, 0)
        elif key == "PGDN":
            self.selected = min(self.selected + 10, max(n - 1, 0))
        elif key == "PGUP":
            self.selected = max(self.selected - 10, 0)
        elif key in ("HOME", "g"):
            self.selected = 0
        elif key in ("END", "G"):
            self.selected = max(n - 1, 0)
        elif key in ("RIGHT", "n"):
            self.next_page(+1)
        elif key in ("LEFT", "p"):
            self.next_page(-1)
        elif key == "ENTER":
            self.open_details()
        elif key == "s":
            self.sort = self.sort.next()
            self._rebuild_view()
            self.set_status(f"Сортировка: {self.sort.label}")
        elif key == "f":
            self.form = FilterForm(self.filter, self.categories)
        elif key == "/":
            self._go_search()
        elif key == "r":
            self.retry()
        elif key in ("ESC", "q"):
            self.screen = Screen.SEARCH
            self.hist_sel = None
        return True

    def next_page(self, delta: int) -> None:
        if self.page is None or self.loading:
            return
        target = self.page.page + delta
        if target < 1:
            self.set_status("Это первая страница")
        elif target > self.page.total_pages:
            self.set_status("Это последняя страница")
        else:
            self._fetch_page(self.query, self.query_category, target)

    def _key_details(self, key: str) -> bool:
        if key in ("DOWN", "j"):
            self.details_scroll += 1
        elif key in ("UP", "k"):
            self.details_scroll = max(0, self.details_scroll - 1)
        elif key == "PGDN":
            self.details_scroll += 10
        elif key == "PGUP":
            self.details_scroll = max(0, self.details_scroll - 10)
        elif key in ("HOME", "g"):
            self.details_scroll = 0
        elif key == "m":
            self.show_magnet()
        elif key == "d":
            self.download()
        elif key == "r":
            self.retry()
        elif key == "/":
            self._go_search()
        elif key in ("ESC", "q"):
            self.screen = Screen.RESULTS
        return True

    def _key_form(self, key: str) -> None:
        form = self.form
        assert form is not None
        name = form.field
        if key == "ESC":
            self.form = None
        elif key == "ENTER":
            try:
                self.filter = form.build()
            except ValueError as e:
                form.error = str(e)
                return
            self.form = None
            self._rebuild_view()
            if self.filter.active:
                self.set_status(f"Фильтр: {self.filter.describe()}, показано {len(self.view)}")
            else:
                self.set_status("Фильтр сброшен")
        elif key in ("DOWN", "TAB"):
            form.focus = (form.focus + 1) % len(form.FIELDS)
        elif key in ("UP", "BTAB"):
            form.focus = (form.focus - 1) % len(form.FIELDS)
        elif name == "category" and key in ("RIGHT", "LEFT", " "):
            step = -1 if key == "LEFT" else 1
            form.cat_index = (form.cat_index + step) % len(form.categories)
        elif key == "c":
            form.reset()
        elif name != "category":
            if key == "BACKSPACE":
                form.text[name] = form.text[name][:-1]
            elif key == "\x15":
                form.text[name] = ""
            elif len(key) == 1 and key in form.ALLOWED[name] and len(form.text[name]) < 12:
                form.text[name] += key
            form.error = ""


def safe_filename(title: str) -> str:
    name = re.sub(r"[^\w.\-()+]+", " ", title).strip(" ._")
    name = re.sub(r"\s+", "_", name)
    return (name or "torrent")[:120]


def _short_path(path: Path) -> str:
    home = str(Path.home())
    s = str(path)
    return "~" + s[len(home):] if s.startswith(home) else s


def _log_exception(exc: BaseException) -> None:
    """Unexpected errors go to a log file instead of the screen."""
    try:
        log = config_dir() / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass
