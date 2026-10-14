"""Runtime кастомных команд живёт в discord_bot/commands.py.

Этот файл оставлен как точка расширения для валидации definition
на стороне агента (например, проверка, что упомянутые role_id
действительно существуют в гильдии перед выполнением).
"""
from __future__ import annotations

from typing import Any

import discord


def validate_definition(defn: dict[str, Any], guild: discord.Guild) -> list[str]:
    """Возвращает список предупреждений. Пустой список — всё ок."""
    problems: list[str] = []
    for action in defn.get("actions") or []:
        t = action.get("type")
        if t in ("give_role", "remove_role"):
            rid = action.get("roleId")
            if not rid or guild.get_role(int(rid)) is None:
                problems.append(f"role {rid} not found in guild {guild.id}")
        if t == "send_message":
            cid = action.get("channelId")
            if not cid or guild.get_channel(int(cid)) is None:
                problems.append(f"channel {cid} not found in guild {guild.id}")
    return problems