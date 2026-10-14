"""Discord gateway client used by the long-running agent."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import discord

from ..core.config_store import ConfigStore
from . import events

log = logging.getLogger("agent.discord")

GuildSync = Callable[[dict], Awaitable[None]]
ClientReady = Callable[[discord.Client], Awaitable[None]]


class BotClient(discord.Client):
    def __init__(
        self,
        store: ConfigStore,
        on_guilds_sync: GuildSync,
        on_client_ready: ClientReady,
    ) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.bans = True
        super().__init__(intents=intents)
        self.store = store
        self.on_guilds_sync = on_guilds_sync
        self.on_client_ready = on_client_ready
        events.register(self, store)

    async def on_ready(self) -> None:
        log.info("connected to Discord as %s", self.user)
        await self.on_client_ready(self)
        await self.sync_guilds()

    async def on_guild_join(self, _guild: discord.Guild) -> None:
        await self.sync_guilds()

    async def on_guild_remove(self, _guild: discord.Guild) -> None:
        await self.sync_guilds()

    async def sync_guilds(self) -> None:
        await self.on_guilds_sync({
            "guilds": [
                {
                    "id": str(guild.id),
                    "name": guild.name,
                    "icon": guild.icon.url if guild.icon else None,
                    "memberCount": guild.member_count or 0,
                    "channels": [
                        {"id": str(channel.id), "name": channel.name, "type": channel_type}
                        for channel in guild.channels
                        if (channel_type := channel_type_for(channel)) is not None
                    ],
                    "roles": [
                        {
                            "id": str(role.id),
                            "name": role.name,
                            "color": role.color.value,
                        }
                        for role in guild.roles
                    ],
                }
                for guild in self.guilds
            ],
        })


def channel_type_for(channel: discord.abc.GuildChannel) -> str | None:
    if isinstance(channel, discord.TextChannel):
        return "announcement" if channel.is_news() else "text"
    if isinstance(channel, discord.VoiceChannel):
        return "voice"
    if isinstance(channel, discord.CategoryChannel):
        return "category"
    if isinstance(channel, discord.ForumChannel):
        return "forum"
    return None


async def run_bot(
    store: ConfigStore,
    on_guilds_sync: GuildSync,
    token: str,
    on_client_ready: ClientReady,
) -> None:
    client = BotClient(store, on_guilds_sync, on_client_ready)
    try:
        await client.start(token)
    finally:
        await client.close()