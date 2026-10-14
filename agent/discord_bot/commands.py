"""Синхронизация slash-команд с Discord по данным config_store.

Команды создаются из definition_json, который кладёт пользователь
в UI. Агент превращает его в discord.app_commands.Command.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands

from ..core.config_store import CommandState, ConfigStore

log = logging.getLogger("agent.commands")

# Кэш зарегистрированных команд: (guild_id, name) → Command
_registered: dict[tuple[str, str], app_commands.Command] = {}


def _build_command(state: CommandState) -> app_commands.Command:
    d = state.definition
    name = d["name"]
    description = d.get("description") or ""

    async def callback(interaction: discord.Interaction, **kwargs) -> None:
        await _execute(interaction, state, kwargs)

    cmd = app_commands.Command(
        name=name,
        description=description,
        callback=callback,
    )
    # TODO: добавить options из d.get("options") по мере необходимости
    return cmd


async def _execute(interaction: discord.Interaction, state: CommandState, kwargs: dict) -> None:
    actions = state.definition.get("actions") or []
    for action in actions:
        t = action.get("type")
        try:
            if t == "reply":
                await interaction.response.send_message(
                    action.get("text", ""),
                    ephemeral=bool(action.get("ephemeral")),
                )
            elif t == "send_message":
                channel = interaction.guild.get_channel(int(action["channelId"]))
                if channel:
                    await channel.send(action.get("text", ""))
            elif t == "give_role":
                role = interaction.guild.get_role(int(action["roleId"]))
                if role and isinstance(interaction.user, discord.Member):
                    await interaction.user.add_roles(role)
            elif t == "remove_role":
                role = interaction.guild.get_role(int(action["roleId"]))
                if role and isinstance(interaction.user, discord.Member):
                    await interaction.user.remove_roles(role)
            elif t == "dm":
                await interaction.user.send(action.get("text", ""))
        except Exception:
            log.exception("command action failed: %s", t)


async def sync_commands(client: discord.Client, store: ConfigStore) -> None:
    """Перестроить slash-команды по текущему состоянию config_store."""
    for guild in client.guilds:
        guild_id = str(guild.id)
        wanted = {c.name: c for c in store.commands_for_guild(guild_id) if c.enabled}

        # Удалить лишние
        for (gid, name), cmd in list(_registered.items()):
            if gid == guild_id and name not in wanted:
                try:
                    client.tree.remove_command(cmd.name, guild=guild)
                except Exception:
                    pass
                _registered.pop((gid, name), None)

        # Добавить/обновить
        for name, state in wanted.items():
            key = (guild_id, name)
            if key in _registered:
                continue
            cmd = _build_command(state)
            client.tree.add_command(cmd, guild=guild, override=True)
            _registered[key] = cmd

    try:
        await client.tree.sync()
        log.info("commands synced")
    except Exception:
        log.exception("tree sync failed")