"""discord.py клиент. Запускается в фоне, событий подключаются к модулям."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from ..core.config_store import ConfigStore
from ..secrets import get_discord_token

log = logging.getLogger("agent.discord")


class BotClient(discord.Client):
    def __init__(self, store: ConfigStore, on_guilds_sync: "GuildsSyncFn", intents: discord.Intents):
        super().__init__(intents=intents)
        self.store = store
        self._on_guilds_sync = on_guilds_sync

    async def on_ready(self) -> None:
        log.info("logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        await self._push_guilds_sync()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._push_guilds_sync()

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self._on_guilds_sync({
            "guildId": str(guild.id),
            "event": "left",
        })

    async def _push_guilds_sync(self) -> None:
        guilds: list[dict[str, Any]] = []
        for g in self.guilds:
            channels = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "type": _channel_type(c),
                }
                for c in g.channels
                if isinstance(c, (discord.TextChannel, discord.VoiceChannel,
                                  discord.CategoryChannel, discord.ForumChannel))
            ]
            roles = [
                {"id": str(r.id), "name": r.name, "color": r.color.value}
                for r in g.roles
                if not r.is_default()
            ]
            guilds.append({
                "id": str(g.id),
                "name": g.name,
                "icon": str(g.icon.url) if g.icon else None,
                "memberCount": g.member_count or 0,
                "channels": channels,
                "roles": roles,
            })
        await self._on_guilds_sync({"guilds": guilds})


def _channel_type(c: discord.abc.GuildChannel) -> str:
    if isinstance(c, discord.TextChannel):
        if c.is_news():
            return "announcement"
        return "text"
    if isinstance(c, discord.VoiceChannel):
        return "voice"
    if isinstance(c, discord.ForumChannel):
        return "forum"
    if isinstance(c, discord.CategoryChannel):
        return "category"
    return "text"


GuildsSyncFn = "Callable[[dict[str, Any]], Awaitable[None]]"


async def run_bot(store: ConfigStore, on_guilds_sync) -> None:
    """Запуск discord.py клиента. Блокирует до отключения."""
    token = get_discord_token()
    if not token:
        raise RuntimeError("Discord token is missing (run pairing)")

    intents = discord.Intents.default()
    intents.members = True          # privileged, нужен для welcome
    intents.message_content = True  # privileged, нужен для логов/модерации
    intents.guilds = True
    intents.voice_states = False

    client = BotClient(store=store, on_guilds_sync=on_guilds_sync, intents=intents)

    # События модулей подключаются через cog-like регистрацию
    from . import events as events_module
    events_module.register(client, store)

    await client.start(token)