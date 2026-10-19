"""Entry point: python3 -m torrseek  or  torrseek"""
from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="torrseek", description="Терминальный поиск торрентов")
    p.add_argument("--adapter", choices=("mock", "http"), help="переопределить адаптер из конфига")
    p.add_argument("--config", help="путь к config.toml")
    p.add_argument("--version", action="version", version=f"TorrSeek {__version__}")
    args = p.parse_args(argv)

    from . import config
    from .api.base import ApiError

    try:
        cfg = config.load(args.config)
        if args.adapter:
            cfg.adapter = args.adapter
        client = config.make_client(cfg)
    except (config.ConfigError, ApiError, ValueError, TypeError) as e:
        print(f"torrseek: ошибка конфигурации: {e}", file=sys.stderr)
        return 2

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("torrseek: нужен интерактивный терминал", file=sys.stderr)
        return 2

    from .app import App
    from .ui import tui

    try:
        tui.run(App(client, cfg))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
