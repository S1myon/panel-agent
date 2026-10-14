"""Подключение событий Discord к модулям.

Каждое событие читает актуальные настройки из config_store.
Если модуль выключен — обработчик сразу выходит.
"""
from __future__ import annotations

import logging

import discord

from ..core.config_store import ConfigStore
from ..modules import welcome, logs, moderation, stats

log = logging.getLogger("agent.events")


def register(client: discord.Client, store: ConfigStore) -> None:

    @client.event
    async def on_member_join(member: discord.Member) -> None:
        guild_id = str(member.guild.id)
        try:
            if store.is_enabled(guild_id, "welcome"):
                await welcome.on_member_join(member, store.get_settings(guild_id, "welcome"))
            if store.is_enabled(guild_id, "logs"):
                await logs.on_member_join(member, store.get_settings(guild_id, "logs"))
            if store.is_enabled(guild_id, "stats"):
                await stats.on_member_join(member, store.get_settings(guild_id, "stats"))
        except Exception:
            log.exception("on_member_join handler failed")

    @client.event
    async def on_member_remove(member: discord.Member) -> None:
        guild_id = str(member.guild.id)
        try:
            if store.is_enabled(guild_id, "welcome"):
                await welcome.on_member_remove(member, store.get_settings(guild_id, "welcome"))
            if store.is_enabled(guild_id, "logs"):
                await logs.on_member_remove(member, store.get_settings(guild_id, "logs"))
        except Exception:
            log.exception("on_member_remove handler failed")

    @client.event
    async def on_message_delete(message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        guild_id = str(message.guild.id)
        try:
            if store.is_enabled(guild_id, "logs"):
                await logs.on_message_delete(message, store.get_settings(guild_id, "logs"))
        except Exception:
            log.exception("on_message_delete handler failed")

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        guild_id = str(message.guild.id)
        try:
            if store.is_enabled(guild_id, "moderation"):
                await moderation.on_message(message, store.get_settings(guild_id, "moderation"))
            if store.is_enabled(guild_id, "stats"):
                await stats.on_message(message, store.get_settings(guild_id, "stats"))
        except Exception:
            log.exception("on_message handler failed")

    @client.event
    async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
        guild_id = str(guild.id)
        try:
            if store.is_enabled(guild_id, "logs"):
                await logs.on_member_ban(guild, user, store.get_settings(guild_id, "logs"))
        except Exception:
            log.exception("on_member_ban handler failed")