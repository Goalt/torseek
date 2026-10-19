"""Pure rendering: App state -> list of rows (segments of text + style).

No curses here, so layouts can be checked at any width in tests.
Every row is exactly `w` cells wide.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..app import App, Screen
from ..models import human_size
from . import text as tx

MIN_W, MIN_H = 40, 10
WIDE = 60  # from this width on, the leechers and date columns are shown

Seg = tuple[str, str]  # (text, style); styles: normal bold dim header sel error ok accent
Row = tuple[Seg, ...]


@dataclass
class Frame:
    rows: list[Row]
    cursor: tuple[int, int] | None = None


def line(text: str, w: int, style: str = "normal") -> Row:
    return ((tx.pad(text, w), style),)


def segs(w: int, *parts: Seg, fill: str = "normal") -> Row:
    out, used = [], 0
    for t, st in parts:
        t = tx.truncate(t, w - used, mark="")
        if not t:
            continue
        out.append((t, st))
        used += tx.width(t)
    if used < w:
        out.append((" " * (w - used), fill))
    return tuple(out)


def render(app: App, w: int, h: int) -> Frame:
    if w < MIN_W or h < MIN_H:
        msg = tx.wrap(f"Окно {w}x{h}, нужно минимум {MIN_W}x{MIN_H}", max(w, 1))
        rows = [line(m, w) for m in msg[:h]]
        return Frame(rows + [line("", w)] * (h - len(rows)))

    titles = {Screen.SEARCH: "Поиск", Screen.RESULTS: "Результаты", Screen.DETAILS: "Карточка"}
    name = "Фильтр" if app.form else titles[app.screen]
    header = line(f" TorrSeek | {name}", w, "header")
    body_h = h - 3
    cursor = None
    if app.screen is Screen.SEARCH:
        body, cursor = _search(app, w, body_h)
    elif app.form is not None:
        body = _form(app, w, body_h)
    elif app.screen is Screen.RESULTS:
        body = _results(app, w, body_h)
    else:
        body = _details(app, w, body_h)
    body = body[:body_h] + [line("", w)] * (body_h - len(body))
    if cursor is not None:
        cursor = (cursor[0] + 1, cursor[1])
    return Frame([header] + body + [_hints(app, w), _status(app, w)], cursor)


# ------------------------------------------------------------------ parts
def _hints(app: App, w: int) -> Row:
    if app.form:
        t = " Enter ok  Esc отмена  c сброс  <- -> категория"
    elif app.screen is Screen.SEARCH:
        t = " Enter искать  Tab категория  Up/Dn история  Esc очистить/выход"
    elif app.screen is Screen.RESULTS:
        t = " Enter карточка  n/p стр.  s сорт  f фильтр  / поиск  q назад"
    else:
        t = " m magnet  d .torrent  j/k листать  / поиск  q назад"
    return line(t, w, "dim")


def _status(app: App, w: int) -> Row:
    if app.loading:
        return line(f" {app.spinner_frame()} {app.loading_label}...  Esc отмена", w, "accent")
    if app.status:
        return line(" " + tx.clean(app.status), w, "error" if app.status_error else "ok")
    return line("", w)


def _search(app: App, w: int, h: int):
    rows = [line("", w), line(" Запрос:", w, "bold")]
    avail = w - 4
    start = 0
    while tx.width(app.input[start:app.cursor]) > avail - 1:
        start += 1
    visible = tx.hard_split(app.input[start:], avail) if app.input[start:] else ""
    rows.append(segs(w, (" > ", "accent"), (visible, "normal")))
    cursor = (2, 3 + tx.width(app.input[start:app.cursor]))
    cat = app.search_category or "все"
    rows.append(line("", w))
    rows.append(segs(w, (" Категория: ", "normal"), (f"< {cat} >", "accent"), ("  Tab", "dim")))
    rows.append(line("", w))
    if not app.history:
        rows.append(line(" История пуста", w, "dim"))
    else:
        rows.append(line(" История:", w, "bold"))
        for i, q in enumerate(app.history):
            if len(rows) >= h:
                break
            style = "sel" if i == app.hist_sel else "normal"
            rows.append(line(f"  {i + 1:>2}. {tx.clean(q)}", w, style))
    return rows, cursor


def _fmt_count(n: int) -> str:
    return str(n) if n < 100_000 else f"{n // 1000}k"


def _results(app: App, w: int, h: int) -> list[Row]:
    page = app.page
    if page is None:
        return [line(" Нет результатов", w, "dim")]
    info = f" стр {page.page}/{max(page.total_pages, 1)}  {page.total_found} шт  сорт: {app.sort.label}"
    if app.query_category:
        info += f"  [{app.query_category}]"
    info += f"  '{tx.clean(app.query)}'"
    if app.filter.active:
        info += f"  фильтр: {app.filter.describe()}"
    rows = [line(info, w, "bold")]

    wide = w >= WIDE
    fixed = (1 + 6) + (1 + 6) + ((1 + 5) + (1 + 10) if wide else 0)
    tw = w - 1 - fixed
    head = " " + tx.pad("Название", tw) + " " + tx.rjust("Размер", 6) + " " + tx.rjust("S", 6)
    if wide:
        head += " " + tx.rjust("L", 5) + " " + tx.pad("Дата", 10)
    rows.append(line(head, w, "dim"))

    list_h = h - 2
    if not app.view:
        msg = "Ничего не найдено" if page.total_found == 0 else "Нет раздач под фильтр (f)"
        rows.append(line(" " + msg, w, "dim"))
        return rows
    if app.selected < app.results_top:
        app.results_top = app.selected
    elif app.selected >= app.results_top + list_h:
        app.results_top = app.selected - list_h + 1
    app.results_top = max(0, min(app.results_top, max(0, len(app.view) - list_h)))
    for i in range(app.results_top, min(len(app.view), app.results_top + list_h)):
        t = app.view[i]
        s = " " + tx.pad(tx.clean(t.title), tw) + " " + tx.rjust(human_size(t.size_bytes), 6) \
            + " " + tx.rjust(_fmt_count(t.seeders), 6)
        if wide:
            s += " " + tx.rjust(_fmt_count(t.leechers), 5) + " " + t.uploaded_at.strftime("%Y-%m-%d")
        rows.append(line(s, w, "sel" if i == app.selected else "normal"))
    return rows


def details_lines(app: App, w: int) -> list[Row]:
    d = app.details
    if d is None:
        return []
    inner = w - 2
    out: list[Row] = []

    def add(text: str, style: str = "normal"):
        out.append(line(" " + text, w, style))

    for t in tx.wrap(tx.clean(d.title), inner):
        add(t, "bold")
    add("")
    add(f"Размер: {human_size(d.size_bytes)} ({d.size_bytes:,} Б)".replace(",", " "))
    add(f"Сиды: {d.seeders}  Личи: {d.leechers}")
    add(f"Категория: {d.category}  Дата: {d.uploaded_at:%Y-%m-%d}")
    add("Infohash:", "dim")
    for c in tx.chunks(d.infohash, inner):
        add(c, "accent")
    if d.description:
        add("")
        for t in tx.wrap(tx.clean(d.description), inner):
            add(t)
    add("")
    add(f"Файлы ({len(d.files)}):", "bold")
    for f in d.files:
        add(tx.rjust(human_size(f.size_bytes), 6) + " " + tx.truncate_left(tx.clean(f.path), inner - 7))
    add("")
    add("Magnet (m - вывести для копирования):", "bold")
    for c in tx.chunks(d.magnet, inner):
        add(c, "accent")
    return out


def _details(app: App, w: int, h: int) -> list[Row]:
    lines = details_lines(app, w)
    app.details_scroll = max(0, min(app.details_scroll, max(0, len(lines) - h)))
    return lines[app.details_scroll:app.details_scroll + h]


def _form(app: App, w: int, h: int) -> list[Row]:
    f = app.form
    assert f is not None
    rows = [line("", w), line(" Фильтр по текущей странице", w, "bold"), line("", w)]
    for i, name in enumerate(f.FIELDS):
        label = tx.pad(f.LABELS[name] + ":", 12)
        value = f.value_text(name)
        shown = f"< {value} >" if name == "category" else f"[{value}{'_' if i == f.focus else ''}]"
        rows.append(segs(w, ("  " + label + " ", "normal"), (shown, "sel" if i == f.focus else "accent")))
    rows.append(line("", w))
    rows.append(line("  Размер: 700M, 1.5G, 500 (= МБ)", w, "dim"))
    if f.error:
        for t in tx.wrap(f.error, w - 2):
            rows.append(line(" " + t, w, "error"))
    return rows
