"""Configuration: ~/.config/torrseek/config.toml plus TORRSEEK_* env vars.

Example config.toml:

    adapter = "mock"            # or "http"
    base_url = "https://api.example.org"
    token = "..."               # or TORRSEEK_TOKEN; never logged
    timeout = 15
    mock_delay = [0.2, 0.6]     # seconds, min/max
    download_dir = "~/Downloads/torrseek"
    categories = ["linux", "software", "video", "audio", "books", "dataset"]
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import DEFAULT_CATEGORIES


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "torrseek"


@dataclass
class Config:
    adapter: str = "mock"
    base_url: str = ""
    token: str | None = field(default=None, repr=False)
    timeout: float = 15.0
    mock_delay: tuple[float, float] = (0.2, 0.6)
    download_dir: Path = field(default_factory=lambda: Path("~/Downloads/torrseek").expanduser())
    categories: tuple[str, ...] = DEFAULT_CATEGORIES
    history_file: Path = field(default_factory=lambda: config_dir() / "history.txt")


class ConfigError(Exception):
    pass


def load(path: str | Path | None = None, env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    path = Path(path or env.get("TORRSEEK_CONFIG") or config_dir() / "config.toml")
    cfg = Config()
    if path.exists():
        import tomllib  # imported lazily: most runs have no config file

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as e:
            raise ConfigError(f"{path}: {e}") from None
        cfg.adapter = str(data.get("adapter", cfg.adapter))
        cfg.base_url = str(data.get("base_url", cfg.base_url))
        cfg.token = data.get("token") or None
        cfg.timeout = float(data.get("timeout", cfg.timeout))
        if "mock_delay" in data:
            lo, hi = data["mock_delay"]
            cfg.mock_delay = (float(lo), float(hi))
        if "download_dir" in data:
            cfg.download_dir = Path(str(data["download_dir"])).expanduser()
        if "categories" in data:
            cfg.categories = tuple(str(c) for c in data["categories"])
    cfg.adapter = env.get("TORRSEEK_ADAPTER", cfg.adapter)
    cfg.token = env.get("TORRSEEK_TOKEN", cfg.token)
    if env.get("TORRSEEK_BASE_URL"):
        cfg.base_url = env["TORRSEEK_BASE_URL"]
    if env.get("TORRSEEK_MOCK_DELAY"):
        lo, _, hi = env["TORRSEEK_MOCK_DELAY"].partition(",")
        cfg.mock_delay = (float(lo), float(hi or lo))
    return cfg


def make_client(cfg: Config):
    if cfg.adapter == "mock":
        from .api.mock import MockClient

        return MockClient(delay=cfg.mock_delay)
    if cfg.adapter == "http":
        from .api.http import HttpClient

        return HttpClient(cfg.base_url, cfg.token, timeout=cfg.timeout)
    raise ConfigError(f"unknown adapter {cfg.adapter!r} (expected 'mock' or 'http')")
