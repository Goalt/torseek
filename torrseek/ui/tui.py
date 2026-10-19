"""curses front end: key reading, diff drawing, magnet output."""
from __future__ import annotations

import base64
import curses
import os
import sys

from ..app import App
from .render import Frame, render
from .text import width

STYLES = ("normal", "bold", "dim", "header", "sel", "error", "ok", "accent")


def osc52(text: str) -> str:
    """Terminal escape that asks the terminal to put text into the clipboard."""
    return "\033]52;c;" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "\a"


def _attrs() -> dict[str, int]:
    a = {s: curses.A_NORMAL for s in STYLES}
    a.update(bold=curses.A_BOLD, dim=curses.A_DIM, header=curses.A_REVERSE | curses.A_BOLD,
             sel=curses.A_REVERSE, error=curses.A_BOLD, accent=curses.A_NORMAL)
    if curses.has_colors():
        try:
            curses.start_color()
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        try:
            curses.init_pair(1, curses.COLOR_RED, bg)
            curses.init_pair(2, curses.COLOR_GREEN, bg)
            curses.init_pair(3, curses.COLOR_CYAN, bg)
            a["error"] = curses.color_pair(1) | curses.A_BOLD
            a["ok"] = curses.color_pair(2)
            a["accent"] = curses.color_pair(3)
        except curses.error:
            pass
    return a


KEYMAP = {
    curses.KEY_UP: "UP", curses.KEY_DOWN: "DOWN", curses.KEY_LEFT: "LEFT",
    curses.KEY_RIGHT: "RIGHT", curses.KEY_ENTER: "ENTER", curses.KEY_BACKSPACE: "BACKSPACE",
    curses.KEY_DC: "DELETE", curses.KEY_HOME: "HOME", curses.KEY_END: "END",
    curses.KEY_PPAGE: "PGUP", curses.KEY_NPAGE: "PGDN", curses.KEY_RESIZE: "RESIZE",
    curses.KEY_BTAB: "BTAB",
}
CHARMAP = {"\n": "ENTER", "\r": "ENTER", "\x1b": "ESC", "\x7f": "BACKSPACE",
           "\x08": "BACKSPACE", "\t": "TAB"}


# Escape sequences that curses may not decode (terminal not in keypad mode,
# or terminfo that does not match what the terminal really sends).
ESCSEQ = {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT", "OA": "UP", "OB": "DOWN",
          "OC": "RIGHT", "OD": "LEFT", "[H": "HOME", "[F": "END", "OH": "HOME", "OF": "END",
          "[1~": "HOME", "[4~": "END", "[3~": "DELETE", "[5~": "PGUP", "[6~": "PGDN", "[Z": "BTAB"}


def read_escape(scr) -> str:
    """Called after a bare ESC: read the rest of a sequence if one follows."""
    seq = ""
    scr.nodelay(True)
    try:
        while len(seq) < 4:
            try:
                ch = scr.get_wch()
            except curses.error:
                break
            if not isinstance(ch, str):
                break
            seq += ch
            if seq in ESCSEQ:
                return ESCSEQ[seq]
            if ch.isalpha() or ch == "~":
                break
    finally:
        scr.nodelay(False)
    return "ESC" if not seq else "UNKNOWN"


def normalize(ch) -> str | None:
    if isinstance(ch, int):
        return KEYMAP.get(ch)
    return CHARMAP.get(ch, ch)


class Painter:
    """Redraws only the rows that changed since the previous frame."""

    def __init__(self, scr, attrs: dict[str, int]):
        self.scr = scr
        self.attrs = attrs
        self.prev: list = []
        self.size = (0, 0)

    def invalidate(self) -> None:
        self.prev = []

    def draw(self, frame: Frame) -> int:
        h, w = self.scr.getmaxyx()
        if (h, w) != self.size:
            self.size = (h, w)
            self.prev = []
            self.scr.erase()
        changed = 0
        for y, row in enumerate(frame.rows[:h]):
            if y < len(self.prev) and self.prev[y] == row:
                continue
            changed += 1
            x = 0
            for text, style in row:
                try:  # writing the bottom-right cell raises but still draws
                    self.scr.addstr(y, x, text, self.attrs.get(style, 0))
                except curses.error:
                    pass
                x += width(text)
        self.prev = list(frame.rows)
        try:
            if frame.cursor:
                curses.curs_set(1)
                self.scr.move(*frame.cursor)
            else:
                curses.curs_set(0)
        except curses.error:
            pass
        self.scr.noutrefresh()
        curses.doupdate()
        return changed


def show_magnet(scr, magnet: str) -> None:
    """Leave curses, print the magnet as one long line the user can select
    with a finger (iOS has no clipboard access from iSH), try OSC 52."""
    curses.def_prog_mode()
    curses.endwin()
    out = sys.stdout
    out.write(osc52(magnet))
    out.write("\n\nMagnet-ссылка (выделите и скопируйте):\n\n")
    out.write(magnet + "\n\n")
    out.write("Enter - вернуться в TorrSeek ")
    out.flush()
    try:
        sys.stdin.readline()
    except (KeyboardInterrupt, EOFError):
        pass
    curses.reset_prog_mode()
    scr.clear()
    scr.refresh()


def _main(scr, app: App) -> None:
    curses.cbreak()
    curses.noecho()
    scr.keypad(True)
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    painter = Painter(scr, _attrs())
    while True:
        h, w = scr.getmaxyx()
        painter.draw(render(app, w, h))
        # Block while idle (cheap in iSH); poll 10x/s while a request runs
        # so the spinner (4 fps) and the result show up promptly.
        scr.timeout(100 if app.loading else -1)
        try:
            ch = scr.get_wch()
        except curses.error:
            ch = None
        key = normalize(ch) if ch is not None else None
        if key == "ESC":
            key = read_escape(scr)
        if key == "RESIZE":
            curses.update_lines_cols()
            painter.invalidate()
        elif key is not None and not app.handle_key(key):
            return
        app.poll()
        while app.effects:
            kind, payload = app.effects.pop(0)
            if kind == "magnet":
                show_magnet(scr, payload)
                painter.invalidate()


def run(app: App) -> None:
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(_main, app)
