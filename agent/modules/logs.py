"""Логи событий сервера в указанный канал."""
from __future__ import annotations

import logging
from typing import Any

import discord

log = logging.getLogger("agent.modules.logs")


def _channel(guild: discord.Guild, settings: dict[str, Any]) -> discord.TextChannel | None:
    cid = settings.get("channelId")
    if not cid:
        return None
    c = guild.get_channel(int(cid))
    return c if isinstance(c, discord.TextChannel) else None


def _enabled(settings: dict[str, Any], event: str) -> bool:
    return event in (settings.get("events") or [])


def _ignored(message: discord.Message, settings: dict[str, Any]) -> bool:
    return str(message.channel.id) in (settings.get("ignoreChannelIds") or [])


async def on_member_join(member: discord.Member, settings: dict[str, Any]) -> None:
    if not _enabled(settings, "member_join"):
        return
    ch = _channel(member.guild, settings)
    if not ch:
        return
    try:
        await ch.send(f"→ {member.mention} присоединился")
    except Exception:
        log.exception("log send failed")


async def on_member_remove(member: discord.Member, settings: dict[str, Any]) -> None:
    if not _enabled(settings, "member_leave"):
        return
    ch = _channel(member.guild, settings)
    if not ch:
        return
    try:
        await ch.send(f"← {member} покинул сервер")
    except Exception:
        log.exception("log send failed")


async def on_message_delete(message: discord.Message, settings: dict[str, Any]) -> None:
    if not _enabled(settings, "message_delete") or _ignored(message, settings):
        return
    ch = _channel(message.guild, settings)
    if not ch:
        return
    try:
        content = (message.content or "")[:500]
        await ch.send(f"🗑 Сообщение от {message.author.mention} удалено: {content}")
    except Exception:
        log.exception("log send failed")


async def on_member_ban(guild: discord.Guild, user: discord.User, settings: dict[str, Any]) -> None:
    if not _enabled(settings, "ban"):
        return
    ch = _channel(guild, settings)
    if not ch:
        return
    try:
        await ch.send(f"🔨 {user} забанен")
    except Exception:
        log.exception("log send failed")