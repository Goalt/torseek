"""End-to-end: run the real curses app in a pseudo-terminal, read the screen
with pyte (dev-only dependency), press keys, resize the window."""
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

pyte = pytest.importorskip("pyte")
ROOT = Path(__file__).resolve().parent.parent

KEYS = {"UP": "\x1b[A", "DOWN": "\x1b[B", "RIGHT": "\x1b[C", "LEFT": "\x1b[D",
        "ENTER": "\r", "ESC": "\x1b", "TAB": "\t"}


class Term:
    def __init__(self, cols, rows, tmp, delay="0.2,0.3"):
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.master, slave = pty.openpty()
        self._winsize(slave, cols, rows)
        env = dict(os.environ, TERM="xterm-256color", HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / "cfg"),
                   TORRSEEK_MOCK_DELAY=delay, PYTHONPATH=str(ROOT), LANG="C.UTF-8", LC_ALL="C.UTF-8")
        env.pop("TORRSEEK_ADAPTER", None)
        self.started = time.monotonic()
        self.proc = subprocess.Popen([sys.executable, "-m", "torrseek"], stdin=slave, stdout=slave,
                                     stderr=slave, env=env, cwd=tmp, start_new_session=True)
        os.close(slave)

    @staticmethod
    def _winsize(fd, cols, rows):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def pump(self, timeout=0.1):
        end = time.monotonic() + timeout
        while True:
            r, _, _ = select.select([self.master], [], [], max(0, end - time.monotonic()))
            if not r:
                return
            try:
                data = os.read(self.master, 65536)
            except OSError:
                return
            if not data:
                return
            self.stream.feed(data)

    def text(self):
        return "\n".join(self.screen.display)

    def wait_for(self, needle, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            if needle in self.text():
                return time.monotonic()
        raise AssertionError(f"{needle!r} not on screen:\n{self.text()}")

    def press(self, *keys):
        for k in keys:
            os.write(self.master, KEYS.get(k, k).encode())
            self.pump(0.08)

    def resize(self, cols, rows):
        self._winsize(self.master, cols, rows)
        self.screen.resize(rows, cols)
        self.proc.send_signal(signal.SIGWINCH)
        self.pump(0.3)

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        os.close(self.master)


@pytest.fixture
def term(tmp_path):
    terms = []

    def make(cols, rows, **kw):
        t = Term(cols, rows, tmp_path, **kw)
        terms.append(t)
        return t

    yield make
    for t in terms:
        t.close()


def dump(t, name):
    out = ROOT / "tests" / "screens"
    out.mkdir(exist_ok=True)
    (out / f"{name}.txt").write_text(t.text() + "\n", encoding="utf-8")


def test_full_flow_40_cols(term, tmp_path):
    t = term(40, 20)
    shown = t.wait_for("TorrSeek | Поиск")
    assert shown - t.started < 2.0, "cold start"
    dump(t, "40-search")
    t.press(*"ubuntu", "ENTER")
    t.wait_for("Поиск...")  # spinner line while the mock sleeps
    t.wait_for("Результаты")
    assert "Дата" not in t.text()
    dump(t, "40-results")
    t.press("s")
    t.wait_for("Сортировка: размер")
    t.press("f", "DOWN", *"100", "ENTER")
    t.wait_for("Фильтр: S>=100")
    t.press("j", "ENTER")
    t.wait_for("Карточка")
    t.wait_for("Infohash")
    dump(t, "40-details")
    t.press("d")
    t.wait_for("Сохранено")
    assert list((tmp_path / "Downloads" / "torrseek").glob("*.torrent"))
    t.press("m")
    t.wait_for("Magnet-ссылка")
    assert "magnet:?xt=urn:btih:" in t.text()
    dump(t, "40-magnet")
    t.press("ENTER")
    t.wait_for("Карточка")
    t.press("q")
    t.wait_for("Результаты")
    t.press("q")
    t.wait_for("TorrSeek | Поиск")
    t.press("ESC", "ESC")  # clear the line, then exit
    t.proc.wait(timeout=3)
    assert t.proc.returncode == 0


def test_special_queries_120_cols(term):
    t = term(120, 30, delay="0,0")
    t.wait_for("TorrSeek | Поиск")
    for q, msg in [("__error__", "Ошибка API"), ("__ratelimit__", "подождите 5"),
                   ("__empty__", "Ничего не найдено"), ("__network__", "Нет связи")]:
        t.press("\x15", *q, "ENTER")
        t.wait_for(msg)
        assert "Traceback" not in t.text()
        if t.text().find("Результаты") >= 0:
            t.press("/")
    t.press("\x15", *"e", "ENTER")
    t.wait_for("Дата")
    dump(t, "120-results")
    assert t.proc.poll() is None


def test_resize_40_120_and_too_small(term):
    t = term(120, 30, delay="0,0")
    t.wait_for("TorrSeek")
    t.press(*"linux", "ENTER")
    t.wait_for("Дата")
    t.resize(40, 20)
    t.wait_for("Результаты")
    assert "Дата" not in t.text()
    for row in t.screen.display:
        assert len(row) == 40
    t.resize(30, 10)
    t.wait_for("нужно минимум")
    t.resize(120, 30)
    t.wait_for("Дата")
    assert t.proc.poll() is None
