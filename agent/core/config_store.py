"""In-memory хранилище конфигов + локальный кэш на диск.

Правила:
  - Все операции — под asyncio.Lock (единственный писатель).
  - На каждое событие Discord модуль читает настройки отсюда заново:
    изменения применяются без перезапуска.
  - Кэш на диск нужен, чтобы пережить перезапуск агента, пока
    нет связи с сервером.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import CONFIG_CACHE_PATH


@dataclass
class ModuleState:
    enabled: bool
    settings: dict[str, Any]
    version: int


@dataclass
class CommandState:
    id: str
    guild_id: str
    name: str
    definition: dict[str, Any]
    enabled: bool
    version: int


@dataclass
class ConfigStore:
    # {guild_id: {module: ModuleState}}
    _modules: dict[str, dict[str, ModuleState]] = field(default_factory=dict)
    # {guild_id: {command_id: CommandState}}
    _commands: dict[str, dict[str, CommandState]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ─── Модули ────────────────────────────────────────────
    async def apply_module(
        self,
        guild_id: str,
        module: str,
        enabled: bool,
        settings: dict[str, Any],
        version: int,
    ) -> bool:
        """Возвращает True, если применено (version новее)."""
        async with self._lock:
            guild_map = self._modules.setdefault(guild_id, {})
            current = guild_map.get(module)
            if current and current.version >= version:
                return False
            guild_map[module] = ModuleState(
                enabled=enabled,
                settings=settings,
                version=version,
            )
            await self._persist_locked()
            return True

    def get_module(self, guild_id: str, module: str) -> ModuleState | None:
        return self._modules.get(guild_id, {}).get(module)

    def is_enabled(self, guild_id: str, module: str) -> bool:
        state = self.get_module(guild_id, module)
        return bool(state and state.enabled)

    def get_settings(self, guild_id: str, module: str) -> dict[str, Any]:
        state = self.get_module(guild_id, module)
        return state.settings if state else {}

    def all_versions(self) -> dict[str, int]:
        """{ "guildId:module": version } — для agent.hello."""
        out: dict[str, int] = {}
        for guild_id, mods in self._modules.items():
            for module, state in mods.items():
                out[f"{guild_id}:{module}"] = state.version
        return out

    # ─── Команды ───────────────────────────────────────────
    async def upsert_command(self, cmd: CommandState) -> bool:
        async with self._lock:
            guild_map = self._commands.setdefault(cmd.guild_id, {})
            current = guild_map.get(cmd.id)
            if current and current.version >= cmd.version:
                return False
            guild_map[cmd.id] = cmd
            await self._persist_locked()
            return True

    async def delete_command(self, guild_id: str, command_id: str) -> bool:
        async with self._lock:
            guild_map = self._commands.get(guild_id)
            if not guild_map or command_id not in guild_map:
                return False
            del guild_map[command_id]
            await self._persist_locked()
            return True

    def commands_for_guild(self, guild_id: str) -> list[CommandState]:
        return list(self._commands.get(guild_id, {}).values())

    # ─── Полная синхронизация ──────────────────────────────
    async def full_sync(
        self,
        configs: list[dict[str, Any]],
        commands: list[dict[str, Any]],
    ) -> None:
        async with self._lock:
            new_modules: dict[str, dict[str, ModuleState]] = {}
            for c in configs:
                gid = c["guildId"]
                mod = c["module"]
                new_modules.setdefault(gid, {})[mod] = ModuleState(
                    enabled=bool(c["enabled"]),
                    settings=c.get("settings") or {},
                    version=int(c["version"]),
                )
            self._modules = new_modules

            new_commands: dict[str, dict[str, CommandState]] = {}
            for c in commands:
                gid = c["guildId"]
                new_commands.setdefault(gid, {})[c["id"]] = CommandState(
                    id=c["id"],
                    guild_id=gid,
                    name=c["name"],
                    definition=c.get("definition") or {},
                    enabled=bool(c["enabled"]),
                    version=int(c["version"]),
                )
            self._commands = new_commands
            await self._persist_locked()

    # ─── Персистентность ───────────────────────────────────
    async def _persist_locked(self) -> None:
        data = {
            "modules": {
                gid: {
                    mod: {"enabled": s.enabled, "settings": s.settings, "version": s.version}
                    for mod, s in mods.items()
                }
                for gid, mods in self._modules.items()
            },
            "commands": {
                gid: {
                    cid: {
                        "id": c.id,
                        "guild_id": c.guild_id,
                        "name": c.name,
                        "definition": c.definition,
                        "enabled": c.enabled,
                        "version": c.version,
                    }
                    for cid, c in cmds.items()
                }
                for gid, cmds in self._commands.items()
            },
        }
        try:
            CONFIG_CACHE_PATH.write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # кэш не критичен

    def load_from_disk(self) -> None:
        if not CONFIG_CACHE_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self._modules = {
            gid: {
                mod: ModuleState(
                    enabled=bool(s.get("enabled")),
                    settings=s.get("settings") or {},
                    version=int(s.get("version", 1)),
                )
                for mod, s in mods.items()
            }
            for gid, mods in (data.get("modules") or {}).items()
        }
        self._commands = {
            gid: {
                cid: CommandState(
                    id=c["id"],
                    guild_id=c.get("guild_id", gid),
                    name=c["name"],
                    definition=c.get("definition") or {},
                    enabled=bool(c.get("enabled", True)),
                    version=int(c.get("version", 1)),
                )
                for cid, c in cmds.items()
            }
            for gid, cmds in (data.get("commands") or {}).items()
        }