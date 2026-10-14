"""Сборка всех частей агента в один запуск.

  LinkClient  ←→  Server
      ↓
  Dispatcher → ConfigStore
      ↓
  BotClient (discord.py) + events + commands
"""
from __future__ import annotations

import asyncio
import logging

import discord

from .config import LocalConfig
from .core.config_store import ConfigStore
from .core.dispatcher import ActionExecutor, Dispatcher
from .discord_bot import commands as commands_module
from .discord_bot.client import channel_type_for, run_bot
from .link.client import LinkClient
from .link.protocol import Envelope
from .modules import stats
from .secrets import get_discord_token

log = logging.getLogger("agent.runtime")


async def run(config: LocalConfig) -> None:
    store = ConfigStore()
    store.load_from_disk()

    action_executor = ActionExecutor()
    link_ref: dict[str, LinkClient] = {}
    client_ref: dict[str, discord.Client] = {}

    async def send(type_: str, payload, ref=None) -> None:
        lc = link_ref.get("link")
        if lc is None:
            log.warning("no link to send %s", type_)
            return
        try:
            await lc.send(type_, payload, ref=ref)
        except Exception:
            log.exception("send failed: %s", type_)

    dispatcher = Dispatcher(store, send, action_executor)

    async def on_message(env: Envelope) -> None:
        if env.type in {"config.full_sync", "config.push", "command.upsert", "command.delete"}:
            await dispatcher.handle(env)
            # Пересобрать slash-команды в Discord
            c = client_ref.get("client")
            if c is not None:
                await commands_module.sync_commands(c, store)
            return
        await dispatcher.handle(env)

    def hello_payload() -> dict:
        token = ""
        client = client_ref.get("client")
        if client and client.user:
            token = client.user.name
        return {
            "botId": config.bot_id,
            "agentVersion": config.agent_version,
            "discordUser": {
                "id": str(client.user.id) if client and client.user else "0",
                "name": token or "unknown",
            },
            "configVersions": store.all_versions(),
        }

    async def on_guilds_sync(payload: dict) -> None:
        if "guilds" in payload:
            await link.send("guilds.sync", payload)
        else:
            await link.send("guild.left", payload)

    async def sync_guilds_after_link() -> None:
        client = client_ref.get("client")
        if client is None:
            return
        await on_guilds_sync({
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
                for guild in client.guilds
            ],
        })

    link = LinkClient(
        config=config,
        bot_id=config.bot_id or "",
        on_message=on_message,
        get_hello_payload=hello_payload,
        on_connected=sync_guilds_after_link,
    )
    link_ref["link"] = link

    # Периодический отчёт статистики
    async def stats_loop() -> None:
        while True:
            await asyncio.sleep(300)
            client = client_ref.get("client")
            if client is None:
                continue
            try:
                guild_ids = [str(g.id) for g in client.guilds]
                reports = await stats.flush(guild_ids)
                for r in reports:
                    await link.send("stats.report", r)
            except Exception:
                log.exception("stats flush failed")

    async def on_client_ready(client: discord.Client) -> None:
        client_ref["client"] = client
        await commands_module.sync_commands(client, store)
        link = link_ref.get("link")
        if link is not None and link.connected:
            await link.send("agent.hello", hello_payload())

    async def discord_runner() -> None:
        token = get_discord_token()
        if not token:
            raise RuntimeError("discord_token is missing")
        await run_bot(store, on_guilds_sync, token, on_client_ready)

    tasks = [
        asyncio.create_task(link.run(), name="link"),
        asyncio.create_task(discord_runner(), name="discord"),
        asyncio.create_task(stats_loop(), name="stats"),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()
        await link.close()