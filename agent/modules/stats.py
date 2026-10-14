"""Статистика: считаем события в памяти, раз в 5 минут шлём на сервер.

Реальная агрегация на стороне сервера. Здесь — только счётчики.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

import discord

log = logging.getLogger("agent.modules.stats")

# guild_id → {metric: count}
_counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))


async def on_message(message: discord.Message, settings: dict[str, Any]) -> None:
    if str(message.channel.id) in (settings.get("ignoreChannelIds") or []):
        return
    _counters[str(message.guild.id)]["messages"] += 1


async def on_member_join(member: discord.Member, settings: dict[str, Any]) -> None:
    _counters[str(member.guild.id)]["joins"] += 1


async def flush(guild_ids: list[str]) -> list[dict[str, Any]]:
    """Вызывается планировщиком раз в 5 минут."""
    today = date.today().isoformat()
    out: list[dict[str, Any]] = []
    for gid in guild_ids:
        counters = _counters.get(gid)
        if not counters:
            continue
        out.append({
            "guildId": gid,
            "date": today,
            "metrics": dict(counters),
        })
        counters.clear()
    return out