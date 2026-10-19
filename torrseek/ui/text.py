"""Terminal-width aware string helpers (CJK = 2 cells, combining = 0)."""
from __future__ import annotations

import unicodedata


def char_width(ch: str) -> int:
    o = ord(ch)
    if o < 32 or 0x7F <= o < 0xA0:
        return 0
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def clean(s: str) -> str:
    """Drop control characters (titles come from an API we do not control)."""
    return "".join(ch if ch.isprintable() else " " for ch in s)


def width(s: str) -> int:
    return sum(char_width(c) for c in s)


def truncate(s: str, w: int, mark: str = "~") -> str:
    """Cut s to at most w cells, ending with `mark` when something was cut."""
    if w <= 0:
        return ""
    if width(s) <= w:
        return s
    out, used, limit = [], 0, w - len(mark)
    for ch in s:
        cw = char_width(ch)
        if used + cw > limit:
            break
        out.append(ch)
        used += cw
    return "".join(out) + mark[:w]


def truncate_left(s: str, w: int, mark: str = "~") -> str:
    """Keep the end of s (useful for file paths)."""
    if width(s) <= w:
        return s
    return truncate(s[::-1], w, mark)[::-1]


def pad(s: str, w: int) -> str:
    s = truncate(s, w)
    return s + " " * (w - width(s))


def rjust(s: str, w: int) -> str:
    s = truncate(s, w)
    return " " * (w - width(s)) + s


def wrap(s: str, w: int) -> list[str]:
    """Word wrap to w cells; words longer than w are split hard."""
    if w <= 0:
        return []
    lines: list[str] = []
    for para in s.split("\n"):
        line, lw = "", 0
        for word in para.split(" "):
            ww = width(word)
            if lw and lw + 1 + ww <= w:
                line, lw = line + " " + word, lw + 1 + ww
                continue
            if lw:
                lines.append(line)
                line, lw = "", 0
            while ww > w:
                head = hard_split(word, w)
                lines.append(head)
                word = word[len(head):]
                ww = width(word)
            line, lw = word, ww
        lines.append(line)
    return lines


def hard_split(s: str, w: int) -> str:
    out, used = [], 0
    for ch in s:
        cw = char_width(ch)
        if used + cw > w:
            break
        out.append(ch)
        used += cw
    return "".join(out) or s[:1]


def chunks(s: str, w: int) -> list[str]:
    """Split without regard to words (for magnet links and hashes)."""
    res = []
    while s:
        head = hard_split(s, w)
        res.append(head)
        s = s[len(head):]
    return res or [""]
