"""Controller flows and layout, without a terminal."""
import pytest

from torrseek.api.base import NetworkError
from torrseek.api.mock import MockClient
from torrseek.app import App, Screen, SyncRunner, ThreadRunner, safe_filename
from torrseek.config import Config
from torrseek.models import Sort
from torrseek.ui import text as tx
from torrseek.ui.render import render


@pytest.fixture
def app(tmp_path):
    cfg = Config(download_dir=tmp_path / "dl", history_file=tmp_path / "history.txt")
    return App(MockClient(delay=(0, 0)), cfg, runner=SyncRunner(), history=[], persist=True)


def type_(app, s):
    for ch in s:
        app.handle_key(ch)


def search(app, q):
    if app.screen is not Screen.SEARCH:
        app.handle_key("/")
    type_(app, q)
    app.handle_key("ENTER")


def plain(frame):
    return ["".join(t for t, _ in row) for row in frame.rows]


# ------------------------------------------------------------------ flows
def test_search_pages_sort(app):
    search(app, "e")
    assert app.screen is Screen.RESULTS
    assert app.page.page == 1 and len(app.view) == 20
    first_ids = [t.id for t in app.view]
    app.handle_key("n")
    assert app.page.page == 2 and [t.id for t in app.view] != first_ids
    app.handle_key("RIGHT")
    assert app.page.page == 3
    app.handle_key("p")
    app.handle_key("LEFT")
    assert app.page.page == 1
    app.handle_key("p")
    assert "первая" in app.status
    # local re-sort, no new request
    calls = []
    orig = app.client.search
    app.client.search = lambda *a, **k: calls.append(1) or orig(*a, **k)
    app.handle_key("s")
    assert app.sort is Sort.SIZE and not calls
    sizes = [t.size_bytes for t in app.view]
    assert sizes == sorted(sizes, reverse=True)
    app.handle_key("s")
    assert app.sort is Sort.DATE
    app.handle_key("s")
    assert app.sort is Sort.SEEDERS


def test_filter_without_new_request(app):
    search(app, "e")
    calls = []
    orig = app.client.search
    app.client.search = lambda *a, **k: calls.append(1) or orig(*a, **k)
    app.handle_key("f")
    assert app.form is not None
    app.handle_key("DOWN")
    type_(app, "100")
    app.handle_key("DOWN")
    type_(app, "1G")
    app.handle_key("ENTER")
    assert app.form is None and not calls
    assert all(t.seeders >= 100 and t.size_bytes >= 1024**3 for t in app.view)
    assert "Фильтр" in app.status
    # bad size keeps the form open with a message
    app.handle_key("f")
    app.handle_key("DOWN"); app.handle_key("DOWN"); app.handle_key("DOWN")
    type_(app, "1..")
    app.handle_key("ENTER")
    assert app.form is not None and app.form.error
    app.handle_key("c")
    app.handle_key("ENTER")
    assert not app.filter.active and len(app.view) == 20


def test_filter_category_cycle(app):
    search(app, "e")
    app.handle_key("f")
    app.handle_key("RIGHT")
    app.handle_key("ENTER")
    assert app.filter.category == "linux"
    assert all(t.category == "linux" for t in app.view)


def test_details_magnet_and_download(app, tmp_path):
    search(app, "big buck")
    app.handle_key("ENTER")
    assert app.screen is Screen.DETAILS
    assert app.details.magnet.startswith("magnet:?")
    app.handle_key("m")
    assert app.effects == [("magnet", app.details.magnet)]
    app.handle_key("d")
    saved = list((tmp_path / "dl").glob("*.torrent"))
    assert len(saved) == 1 and saved[0].read_bytes().startswith(b"d")
    assert "Сохранено" in app.status
    app.handle_key("q")
    assert app.screen is Screen.RESULTS
    app.handle_key("ESC")
    assert app.screen is Screen.SEARCH
    assert app.input == "big buck"  # last query stays editable
    assert app.handle_key("ESC") is True and app.input == ""
    assert app.handle_key("ESC") is False  # search is the root: Esc exits


@pytest.mark.parametrize("query,expect", [
    ("__error__", "Ошибка API"),
    ("__ratelimit__", "подождите 5"),
    ("__network__", "Нет связи"),
    ("__empty__", "Ничего не найдено"),
])
def test_special_queries_give_messages(app, query, expect):
    search(app, query)
    assert expect in app.status
    for w in (40, 120):
        rows = plain(render(app, w, 20))
        assert any(expect in r for r in rows)
        assert not any("Traceback" in r for r in rows)


def test_retry_after_network_error(app):
    calls = {"n": 0}
    orig = app.client.search

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise NetworkError("sleep")
        return orig(*a, **k)

    app.client.search = flaky
    search(app, "debian")
    assert app.status_error and app.screen is Screen.SEARCH
    app.screen = Screen.RESULTS  # 'r' works on results/details screens
    app.handle_key("r")
    assert app.page is not None and app.page.total_found > 0 and not app.status_error


def test_unexpected_exception_does_not_crash(app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    app.client.search = lambda *a, **k: 1 / 0
    search(app, "x")
    assert "Внутренняя ошибка" in app.status


def test_history_keeps_ten_and_navigates(app, tmp_path):
    for i in range(12):
        search(app, f"q{i}")
    assert len(app.history) == 10 and app.history[0] == "q11"
    assert (tmp_path / "history.txt").read_text().splitlines()[0] == "q11"
    app.handle_key("/")
    type_(app, "dra")
    app.handle_key("DOWN")
    assert app.input == "q11"
    app.handle_key("DOWN")
    assert app.input == "q10"
    app.handle_key("UP"); app.handle_key("UP")
    assert app.input == "dra"
    search(app, "q11")
    assert app.history.count("q11") == 1


def test_search_category(app):
    app.handle_key("TAB")
    assert app.search_category == "linux"
    search(app, "e")
    assert all(t.category == "linux" for t in app.view)


def test_empty_query_is_rejected(app):
    app.handle_key("ENTER")
    assert app.status_error and app.page is None


def test_esc_clears_input_then_exits(app):
    type_(app, "abc")
    assert app.handle_key("ESC") is True and app.input == ""
    assert app.handle_key("ESC") is False


def test_thread_runner_spinner_and_timeout():
    t = [0.0]
    app = App(MockClient(delay=(0.05, 0.05)), Config(timeout=1), runner=ThreadRunner(),
              history=[], clock=lambda: t[0], persist=False)
    type_(app, "ubuntu")
    app.handle_key("ENTER")
    assert app.loading
    frames = set()
    for i in range(4):
        t[0] = i * 0.25
        frames.add(app.spinner_frame())
    assert frames == set("|/-\\")
    import time
    time.sleep(0.2)
    app.poll()
    assert not app.loading and app.screen is Screen.RESULTS
    # a request that never returns is abandoned after the timeout
    app.client.search = lambda *a, **k: time.sleep(5)
    app.handle_key("/")
    type_(app, "x")
    app.handle_key("ENTER")
    t[0] = 100
    app.poll()
    assert not app.loading and "время" in app.status


def test_esc_cancels_loading():
    app = App(MockClient(delay=(0.3, 0.3)), runner=ThreadRunner(), history=[], persist=False)
    type_(app, "ubuntu")
    app.handle_key("ENTER")
    app.handle_key("ESC")
    import time
    time.sleep(0.4)
    app.poll()
    assert app.page is None and "отменён" in app.status


# ------------------------------------------------------------------ layout
def all_screens(app):
    """Yield (name, app) for every screen state worth checking."""
    yield "search-empty", app
    search(app, "e")
    yield "results", app
    app.handle_key("f")
    yield "filter", app
    app.handle_key("ESC")
    search(app, "青空")
    yield "results-cjk", app
    app.handle_key("ENTER")
    yield "details-cjk", app
    app.handle_key("/")
    search(app, "Преступление")
    app.handle_key("ENTER")
    yield "details-cyrillic", app
    for _ in range(50):
        app.handle_key("j")
    yield "details-scrolled", app
    app.handle_key("/")
    type_(app, "very long query " * 10)
    yield "search-long-input", app
    app.handle_key("\x15")
    type_(app, "__ratelimit__")
    app.handle_key("ENTER")
    yield "error", app


@pytest.mark.parametrize("w,h", [(40, 12), (40, 24), (60, 20), (80, 24), (120, 40), (39, 20), (120, 5)])
def test_layout_fits(app, w, h):
    for name, a in all_screens(app):
        frame = render(a, w, h)
        assert len(frame.rows) == h, name
        for row in plain(frame):
            assert tx.width(row) == w, (name, w, row)
        if frame.cursor:
            y, x = frame.cursor
            assert 0 <= y < h and 0 <= x < w, name


def test_narrow_hides_date_and_leechers(app):
    search(app, "ubuntu")
    narrow = "\n".join(plain(render(app, 40, 20)))
    wide = "\n".join(plain(render(app, 120, 20)))
    assert "Дата" not in narrow and "Дата" in wide
    assert "2025-" not in narrow and "2025-" in wide


def test_resize_keeps_selection_visible(app):
    search(app, "e")
    for _ in range(19):
        app.handle_key("j")
    for h in (40, 12, 10, 24):
        rows = plain(render(app, 50, h))
        sel = app.view[app.selected].title[:10]
        assert any(sel in r for r in rows), h


def test_no_emoji_or_ambiguous_symbols_in_ui(app):
    import unicodedata
    for name, a in all_screens(app):
        for row in plain(render(a, 80, 30)):
            for ch in row:
                if ord(ch) > 127 and not ch.isalpha():
                    pytest.fail(f"{name}: non-ASCII symbol {ch!r} ({unicodedata.name(ch, '?')})")


def test_safe_filename():
    assert safe_filename("Ubuntu 24.04 / Desktop: amd64?") == "Ubuntu_24.04_Desktop_amd64"
    assert safe_filename("...") == "torrent"


def test_token_not_in_repr():
    from torrseek.api.http import HttpClient
    c = HttpClient("http://x", "supersecret")
    assert "supersecret" not in repr(c)
    assert "supersecret" not in repr(Config(token="supersecret"))
