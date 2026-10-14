from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("agent.modules")


class BaseModule:
    """Интерфейс модуля.

    Настройки читаются из config_store на каждом событии.
    Изменение приходит через config.push и применяется без перезапуска.
    """
    name: str = "base"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled"))