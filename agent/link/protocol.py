"""Envelope WS-протокола и хелперы для отправки/приёма.

Модели payload'ов живут в agent.models.generated (сгенерированы из zod).
Здесь — только обёртка envelope, одинаковая для всех типов.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from ulid import ULID  # из пакета ulid-py; если нет — используем uuid


def _new_id() -> str:
    try:
        return str(ULID())
    except Exception:
        import uuid
        return uuid.uuid4().hex


@dataclass
class Envelope:
    v: int
    id: str
    type: str
    ref: str | None
    ts: int
    payload: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "id": self.id,
            "type": self.type,
            "ref": self.ref,
            "ts": self.ts,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Envelope":
        return cls(
            v=int(d.get("v", 1)),
            id=str(d.get("id", "")),
            type=str(d.get("type", "")),
            ref=d.get("ref"),
            ts=int(d.get("ts", 0)),
            payload=d.get("payload"),
        )


def make(type_: str, payload: Any, ref: str | None = None) -> Envelope:
    return Envelope(
        v=1,
        id=_new_id(),
        type=type_,
        ref=ref,
        ts=int(time.time() * 1000),
        payload=payload,
    )