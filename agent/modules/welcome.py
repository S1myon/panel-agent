"""Приветствие новых участников.

Читает настройки на каждом on_member_join. Поддерживает:
  - текстовое сообщение в канал
  - embed
  - личку
  - авто-роли
  - прощание при выходе
"""
from __future__ import annotations

import logging
from typing import Any

import discord

log = logging.getLogger("agent.modules.welcome")


def _render(text: str, member: discord.Member) -> str:
    return (
        text
        .replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{memberCount}", str(member.guild.member_count or 0))
    )


async def on_member_join(member: discord.Member, settings: dict[str, Any]) -> None:
    guild = member.guild

    # Авто-роли
    auto_roles = settings.get("autoRoleIds") or []
    if auto_roles:
        roles = [guild.get_role(int(rid)) for rid in auto_roles]
        roles = [r for r in roles if r is not None]
        if roles:
            try:
                await member.add_roles(*roles, reason="Auto-role on join")
            except Exception:
                log.exception("failed to add auto-roles")

    # Приветствие в канал
    channel_id = settings.get("channelId")
    if channel_id:
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            text = _render(settings.get("message") or "", member)
            embed_data = settings.get("embed")
            try:
                if embed_data:
                    embed = discord.Embed(
                        title=embed_data.get("title") or None,
                        description=_render(embed_data.get("description") or "", member) or None,
                        color=int(embed_data.get("color") or 0x5865F2),
                    )
                    if img := embed_data.get("imageUrl"):
                        embed.set_image(url=img)
                    await channel.send(content=text or None, embed=embed)
                else:
                    if text:
                        await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
            except Exception:
                log.exception("failed to send welcome message")

    # Личка
    if settings.get("dmEnabled") and settings.get("dmMessage"):
        try:
            await member.send(_render(settings["dmMessage"], member))
        except Exception:
            log.debug("failed to DM %s", member.id)


async def on_member_remove(member: discord.Member, settings: dict[str, Any]) -> None:
    goodbye = settings.get("goodbye") or {}
    if not goodbye.get("enabled"):
        return
    channel_id = goodbye.get("channelId")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if isinstance(channel, discord.TextChannel):
        text = _render(goodbye.get("message") or "", member)
        if text:
            try:
                await channel.send(text)
            except Exception:
                log.exception("failed to send goodbye")