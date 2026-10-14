"""WebSocket-клиент к серверу панели.

Обязанности:
  - Подключиться с Authorization: Bearer <agent_secret> в заголовке апгрейда.
  - Отправить agent.hello, получить hello.ok или config.full_sync.
  - Крутить heartbeat каждые 20 секунд.
  - Принимать config.push / command.upsert / command.delete / action.execute /
    agent.revoke.
  - Пробрасывать события в диспетчер и Discord-клиент.
  - При разрыве — переподключиться с backoff и снова пройти hello.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from ..config import LocalConfig
from ..secrets import get_agent_secret
from .protocol import Envelope, make
from .reconnect import Backoff

log = logging.getLogger("agent.link")

HEARTBEAT_SEC = 20

Handler = Callable[[Envelope], Awaitable[None]]
ConnectedHandler = Callable[[], Awaitable[None]]


class LinkClient:
    def __init__(
        self,
        config: LocalConfig,
        bot_id: str,
        on_message: Callable[[Envelope], Awaitable[None]],
        get_hello_payload: Callable[[], dict[str, Any]],
        on_connected: ConnectedHandler,
    ):
        self.config = config
        self.bot_id = bot_id
        self._on_message = on_message
        self._get_hello_payload = get_hello_payload
        self._on_connected = on_connected

        self._ws: WebSocketClientProtocol | None = None
        self._send_lock = asyncio.Lock()
        self._backoff = Backoff()
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._connect_once()
                self._backoff.reset()
            except Exception as e:
                log.warning("link error: %s", e)
            self._connected.clear()
            if self._stop.is_set():
                break
            await self._backoff.sleep()

    async def _connect_once(self) -> None:
        secret = get_agent_secret()
        if not secret:
            raise RuntimeError("agent_secret is missing (did you run pairing?)")

        headers = {"Authorization": f"Bearer {secret}"}
        log.info("connecting to %s", self.config.ws_url)

        async with websockets.connect(
            self.config.ws_url,
            additional_headers=headers,
            max_size=256 * 1024,
            ping_interval=None,       # свой heartbeat вместо ping/pong
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self._connected.set()
            log.info("connected")

            # Приветствие
            await self.send("agent.hello", self._get_hello_payload())
            await self._on_connected()

            hb_task = asyncio.create_task(self._heartbeat_loop())
            try:
                async for raw in ws:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("bad json from server")
                        continue
                    env = Envelope.from_dict(data)
                    if env.type == "hello.ok":
                        log.info("server: hello.ok")
                        continue
                    await self._on_message(env)
            finally:
                hb_task.cancel()
                try:
                    await hb_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._ws = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SEC)
            if self._ws is None:
                return
            try:
                await self.send("agent.heartbeat", {
                    "latencyMs": 0,
                    "guilds": 0,
                    "uptimeSec": 0,
                })
            except Exception:
                return

    async def send(self, type_: str, payload: Any, ref: str | None = None) -> None:
        if self._ws is None:
            raise RuntimeError("not connected")
        env = make(type_, payload, ref=ref)
        async with self._send_lock:
            await self._ws.send(json.dumps(env.to_dict(), ensure_ascii=False))

    async def close(self) -> None:
        self._stop.set()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return self._connected.is_set()