"""Хранение секретов через системный keyring.

- Discord-токен бота
- agent_secret (выдаётся сервером при pairing)

Если keyring недоступен (Linux без Secret Service, headless-сервер),
используется запасной файл с правами 0600 и предупреждением.
"""
from __future__ import annotations

import os
import stat
import warnings
from pathlib import Path

import keyring
from keyring.errors import KeyringError, NoKeyringError

from .config import DATA_DIR

SERVICE = "DiscordPanelAgent"
DISCORD_TOKEN_KEY = "discord_token"
AGENT_SECRET_KEY = "agent_secret"

_FALLBACK_PATH = DATA_DIR / "secrets.json"


def _keyring_available() -> bool:
    try:
        keyring.get_password(SERVICE, "_probe")
        return True
    except (KeyringError, NoKeyringError):
        return False
    except Exception:
        return False


_use_keyring = _keyring_available()


def _fallback_read() -> dict[str, str]:
    if not _FALLBACK_PATH.exists():
        return {}
    try:
        import json
        return json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fallback_write(data: dict[str, str]) -> None:
    import json
    _FALLBACK_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.chmod(_FALLBACK_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _get(key: str) -> str | None:
    if _use_keyring:
        try:
            return keyring.get_password(SERVICE, key)
        except Exception:
            return None
    return _fallback_read().get(key)


def _set(key: str, value: str) -> None:
    if _use_keyring:
        try:
            keyring.set_password(SERVICE, key, value)
            return
        except Exception:
            pass
    data = _fallback_read()
    data[key] = value
    _fallback_write(data)
    warnings.warn(
        "Keyring недоступен, секреты пишутся в файл. Убедитесь, что диск зашифрован.",
        RuntimeWarning,
    )


def _delete(key: str) -> None:
    if _use_keyring:
        try:
            keyring.delete_password(SERVICE, key)
            return
        except Exception:
            pass
    data = _fallback_read()
    data.pop(key, None)
    _fallback_write(data)


# ─── Публичный API ────────────────────────────────────────

def get_discord_token() -> str | None:
    return _get(DISCORD_TOKEN_KEY)


def set_discord_token(token: str) -> None:
    _set(DISCORD_TOKEN_KEY, token.strip())


def delete_discord_token() -> None:
    _delete(DISCORD_TOKEN_KEY)


def get_agent_secret() -> str | None:
    return _get(AGENT_SECRET_KEY)


def set_agent_secret(secret: str) -> None:
    _set(AGENT_SECRET_KEY, secret.strip())


def delete_agent_secret() -> None:
    _delete(AGENT_SECRET_KEY)


def purge_all() -> None:
    delete_discord_token()
    delete_agent_secret()