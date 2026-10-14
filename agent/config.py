"""Локальная конфигурация агента: пути, сервер, константы.

Всё, что не секрет, хранится в JSON-файле рядом с user-data.
Секреты (Discord-токен, agent_secret) — в keyring (см. secrets.py).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "DiscordPanelAgent"

CONFIG_DIR = Path(user_config_dir(APP_NAME))
DATA_DIR = Path(user_data_dir(APP_NAME))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = CONFIG_DIR / "config.json"
CONFIG_CACHE_PATH = DATA_DIR / "config_cache.json"

DEFAULT_SERVER_URL = "http://localhost:7777"
DEFAULT_WS_URL = "ws://localhost:7777/ws/agent"


@dataclass
class LocalConfig:
    """Не секретные локальные настройки."""
    server_url: str = DEFAULT_SERVER_URL
    ws_url: str = DEFAULT_WS_URL
    bot_id: str | None = None
    agent_version: str = "0.0.1"

    @classmethod
    def load(cls) -> "LocalConfig":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return cls()

    def save(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def env_override(config: LocalConfig) -> LocalConfig:
    """Переопределение через переменные окружения — удобно для тестов и CI."""
    if url := os.environ.get("PANEL_SERVER_URL"):
        config.server_url = url
    if ws := os.environ.get("PANEL_WS_URL"):
        config.ws_url = ws
    return config