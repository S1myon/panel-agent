"""Обработка сообщений от сервера.

Раскладывает config.push / command.upsert / command.delete /
action.execute / agent.revoke по обработчикам.
"""
from __future__ import annotations

import logging
from typing import Any

from ..link.protocol import Envelope
from .config_store import CommandState, ConfigStore

log = logging.getLogger("agent.dispatcher")


class Dispatcher:
    def __init__(
        self,
        store: ConfigStore,
        send: "SendFn",
        action_executor: "ActionExecutor",
    ):
        self.store = store
        self._send = send
        self._actions = action_executor

    async def handle(self, env: Envelope) -> None:
        handler = getattr(self, f"_on_{env.type.replace('.', '_')}", None)
        if handler is None:
            log.warning("unknown message type: %s", env.type)
            return
        try:
            await handler(env)
        except Exception as e:
            log.exception("handler failed for %s: %s", env.type, e)

    # ─── Конфиги ───────────────────────────────────────────
    async def _on_config_push(self, env: Envelope) -> None:
        p = env.payload or {}
        guild_id = p["guildId"]
        module = p["module"]
        version = int(p["version"])
        applied = await self.store.apply_module(
            guild_id=guild_id,
            module=module,
            enabled=bool(p["enabled"]),
            settings=p.get("settings") or {},
            version=version,
        )
        await self._send("config.ack", {
            "guildId": guild_id,
            "module": module,
            "version": version,
            "ok": True,
        })
        if applied:
            log.info("applied %s@%s v%d", module, guild_id, version)

    async def _on_config_full_sync(self, env: Envelope) -> None:
        p = env.payload or {}
        await self.store.full_sync(p.get("configs") or [], p.get("commands") or [])
        log.info("full sync applied: %d configs, %d commands",
                 len(p.get("configs") or []), len(p.get("commands") or []))

    # ─── Команды ───────────────────────────────────────────
    async def _on_command_upsert(self, env: Envelope) -> None:
        p = env.payload or {}
        d = p["definition"]
        await self.store.upsert_command(CommandState(
            id=d["id"],
            guild_id=d["guildId"],
            name=d["name"],
            definition=d.get("definition") or {},
            enabled=bool(d.get("enabled", True)),
            version=int(d.get("version", 1)),
        ))
        log.info("command upserted: %s", d["name"])

    async def _on_command_delete(self, env: Envelope) -> None:
        p = env.payload or {}
        await self.store.delete_command(p["guildId"], p["commandId"])
        log.info("command deleted: %s", p["commandId"])

    # ─── Ручные действия ───────────────────────────────────
    async def _on_action_execute(self, env: Envelope) -> None:
        p = env.payload or {}
        result = await self._actions.execute(
            guild_id=p["guildId"],
            action=p["action"],
            params=p.get("params") or {},
        )
        await self._send("action.result", result, ref=env.id)

    # ─── Отзыв ─────────────────────────────────────────────
    async def _on_agent_revoke(self, env: Envelope) -> None:
        reason = (env.payload or {}).get("reason", "revoked")
        log.warning("agent revoked: %s", reason)
        from ..secrets import delete_agent_secret
        delete_agent_secret()
        raise SystemExit(0)


# Type aliases (для читаемости)
from typing import Awaitable, Callable  # noqa: E402
SendFn = Callable[[str, Any, str | None], Awaitable[None]]


class ActionExecutor:
    """Заглушка. Реальная реализация живёт в discord_bot/actions.py."""

    def __init__(self) -> None:
        self._impl: Callable[..., Awaitable[dict[str, Any]]] | None = None

    def bind(self, impl: Callable[..., Awaitable[dict[str, Any]]]) -> None:
        self._impl = impl

    async def execute(self, guild_id: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._impl is None:
            return {"ok": False, "error": {"code": "NOT_READY", "message": "Discord not ready"}}
        return await self._impl(guild_id, action, params)