"""Модерация: антиспам, плохие слова, ссылки.

Простой in-memory anti-spam: скользящее окно по пользователю.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from typing import Any

import discord

log = logging.getLogger("agent.modules.moderation")

# user_id → deque[timestamp]
_recent: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=20))


async def on_message(message: discord.Message, settings: dict[str, Any]) -> None:
    if not message.content:
        return

    automod = settings.get("automod") or {}

    # Anti-spam
    spam = automod.get("antiSpam") or {}
    if spam.get("enabled"):
        limit = int(spam.get("messages", 5))
        window = float(spam.get("seconds", 3))
        now = time.monotonic()
        dq = _recent[message.author.id]
        dq.append(now)
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            try:
                await message.delete()
                if spam.get("action") == "timeout":
                    await message.author.timeout(
                        discord.utils.utcnow() + __import__("datetime").timedelta(seconds=60),
                        reason="Anti-spam",
                    )
            except Exception:
                log.exception("anti-spam action failed")
            return

    # Bad words
    bw = automod.get("badWords") or {}
    if bw.get("enabled"):
        words = [w.lower() for w in (bw.get("words") or [])]
        lower = message.content.lower()
        if any(w and w in lower for w in words):
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, такие слова запрещены.",
                    delete_after=5,
                )
            except Exception:
                log.exception("bad words action failed")
            return

    # Links
    links = automod.get("links") or {}
    if links.get("enabled"):
        urls = re.findall(r"https?://\S+", message.content)
        whitelist = links.get("whitelist") or []
        for u in urls:
            if not any(w and w in u for w in whitelist):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, ссылки запрещены.",
                        delete_after=5,
                    )
                except Exception:
                    log.exception("link filter action failed")
                return