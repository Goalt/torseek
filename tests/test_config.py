import pytest

from torrseek import config
from torrseek.api.http import HttpClient
from torrseek.api.mock import MockClient


def test_defaults_without_file(tmp_path):
    cfg = config.load(tmp_path / "missing.toml", env={})
    assert cfg.adapter == "mock"
    assert isinstance(config.make_client(cfg), MockClient)


def test_file_and_env(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('adapter = "http"\nbase_url = "https://api.example.org"\ntoken = "from-file"\n'
                 'mock_delay = [0.1, 0.2]\ncategories = ["a", "b"]\n')
    cfg = config.load(p, env={})
    assert (cfg.adapter, cfg.token, cfg.mock_delay, cfg.categories) == ("http", "from-file", (0.1, 0.2), ("a", "b"))
    assert isinstance(config.make_client(cfg), HttpClient)
    cfg = config.load(p, env={"TORRSEEK_ADAPTER": "mock", "TORRSEEK_TOKEN": "from-env"})
    assert cfg.adapter == "mock" and cfg.token == "from-env"


def test_bad_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("adapter = ")
    with pytest.raises(config.ConfigError):
        config.load(p, env={})
    with pytest.raises(config.ConfigError):
        config.make_client(config.Config(adapter="nope"))
