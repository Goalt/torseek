# TorrSeek

Терминальный (curses) поиск торрентов. Чистый Python 3.11+, без сторонних пакетов в рантайме. Работает в iSH на iPhone/iPad и в обычном терминале Linux/macOS. Сейчас работает на мок-API (`MockClient`, 204 записи легального контента).

## Запуск

```sh
# iSH (Alpine)
apk add python3 py3-pip
cd torrseek
python3 -m torrseek          # без установки
pip install . && torrseek    # или как команда
```

Минимальный размер окна 40x10. Задержку мока можно поменять: `TORRSEEK_MOCK_DELAY=0,0 python3 -m torrseek`.

## Управление

| Клавиша | Действие |
|---|---|
| `/` | новый поиск |
| `↑ ↓` / `j k` | перемещение по списку (на экране поиска: история) |
| `→ ←` / `n p` | следующая / предыдущая страница |
| `Enter` | искать / открыть карточку |
| `Tab` | категория поиска (экран поиска) |
| `s` | сортировка: сиды → размер → дата |
| `f` | фильтр: категория, мин. сидов, размер (`700M`, `1.5G`; `c` сброс) |
| `m` | вывести magnet одной строкой + OSC 52 в буфер обмена |
| `d` | сохранить .torrent в `~/Downloads/torrseek/` |
| `r` | повторить упавший запрос |
| `Esc` / `q` | назад; на экране поиска `Esc` очищает строку, второй `Esc` выход |

Пока идёт запрос, в статус-строке крутится спиннер (`Esc` отменяет). Ошибки API показываются там же.

Спецзапросы мока: `__error__`, `__ratelimit__`, `__empty__`, `__network__`.

## Конфиг

`~/.config/torrseek/config.toml` (всё необязательно):

```toml
adapter = "mock"                 # или "http"
base_url = "https://api.example.org"
token = "..."                    # или переменная TORRSEEK_TOKEN
timeout = 15
mock_delay = [0.2, 0.6]
download_dir = "~/Downloads/torrseek"
categories = ["linux", "software", "video", "audio", "books", "dataset"]
```

Переменные окружения: `TORRSEEK_ADAPTER`, `TORRSEEK_TOKEN`, `TORRSEEK_BASE_URL`, `TORRSEEK_CONFIG`, `TORRSEEK_MOCK_DELAY`. История поиска: `~/.config/torrseek/history.txt`, неожиданные ошибки: `~/.config/torrseek/error.log`.

## Структура

```
torrseek/
  __main__.py      точка входа
  app.py           контроллер и состояние (без curses)
  ui/render.py     верстка экранов (чистые функции, тестируется на любой ширине)
  ui/tui.py        curses: клавиши, перерисовка только изменившихся строк, вывод magnet
  ui/text.py       ширина символов, обрезка, перенос
  models.py        dataclass-модели, Sort
  config.py        конфиг и выбор адаптера
  bencode.py, torrentfile.py   сборка .torrent и magnet для мока
  api/base.py      SearchClient, ApiError/NotFound/RateLimited/NetworkError
  api/mock.py      MockClient
  api/http.py      HttpClient по предполагаемым эндпоинтам
  fixtures/torrents.json
tests/
  test_contract.py   контракт SearchClient для всех адаптеров
  test_app.py        контроллер, верстка на 40/60/80/120 колонках
  test_tty.py        настоящий curses в псевдотерминале (нужен pyte)
  mock_server.py     HTTP-сервер с предполагаемым API поверх MockClient
tools/gen_fixtures.py   генератор фикстур
```

## Тесты

```sh
pip install pytest pyte
python3 -m pytest
```

`test_contract.py` гоняется для `mock` и для `http` (HttpClient против `tests/mock_server.py`). Скриншоты экранов из `test_tty.py` пишутся в `tests/screens/`.

## Когда придёт реальный API

1. В `torrseek/api/http.py` поменять пути запросов, авторизацию и функции `_to_item` / `_to_details`.
2. Прогнать `tests/test_contract.py` против него (добавить адаптер в `ADAPTERS` в `tests/conftest.py`).
3. Поставить `adapter = "http"` в конфиге. Мок остаётся для тестов и офлайн-работы.

## Что важно знать

- Сортировка и фильтр работают локально по загруженной странице (без нового запроса). Выбранная сортировка передаётся в API при переходе на другую страницу.
- Фикстуры синтетические: названия реальные, но infohash и куски .torrent сгенерированы, поэтому magnet-ссылки и .torrent из мока ничего не скачают.
- Фикстуры лежат в `torrseek/fixtures/`, а не в корне, чтобы попадать в пакет при `pip install .`.
