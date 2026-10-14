"""Первичная привязка агента и запуск.

Режимы:
  python -m agent              # запустить (если уже привязан)
  python -m agent pair         # привязать: pairing code + Discord token
  python -m agent reset        # стереть секреты
  python -m agent status       # показать состояние
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import re
import sys

import httpx

from . import __version__
from .config import LocalConfig, env_override
from .secrets import (
    get_agent_secret,
    get_discord_token,
    purge_all,
    set_agent_secret,
    set_discord_token,
)

log = logging.getLogger("agent.cli")


def _prompt(msg: str) -> str:
    return input(msg).strip()


def _prompt_hidden(msg: str) -> str:
    return getpass.getpass(msg).strip()


async def cmd_pair(args: argparse.Namespace) -> int:
    config = env_override(LocalConfig.load())

    code = args.code or _prompt("Pairing code: ")
    if not code:
        print("[ERROR] Pairing code не задан", file=sys.stderr)
        return 1

    discord_token = _prompt_hidden("Discord bot token (скрытый ввод): ")
    if not discord_token:
        print("[ERROR] Discord token не задан", file=sys.stderr)
        return 1

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            validation = await client.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {discord_token}"},
            )
    except httpx.RequestError as error:
        print(f"[ERROR] Не удалось связаться с Discord: {error}", file=sys.stderr)
        return 2

    if validation.status_code == 401:
        print("[ERROR] Discord bot token недействителен", file=sys.stderr)
        return 2
    if validation.status_code != 200:
        print(f"[ERROR] Discord вернул HTTP {validation.status_code}", file=sys.stderr)
        return 2
    try:
        identity = validation.json()
    except ValueError:
        print("[ERROR] Discord вернул некорректный ответ", file=sys.stderr)
        return 2
    discord_app_id = identity.get("id") if isinstance(identity, dict) else None
    if not isinstance(discord_app_id, str) or not re.fullmatch(r"\d{17,20}", discord_app_id):
        print("[ERROR] Discord вернул некорректный Application ID", file=sys.stderr)
        return 2

    # Обмен pairing code на agent_secret
    url = config.server_url.rstrip("/") + "/agent/pair"
    print(f"-> Обмен pairing code на {url}")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={"code": code, "label": "cli", "discordAppId": discord_app_id},
            )
    except Exception as e:
        print(f"[ERROR] Не удалось связаться с сервером: {e}", file=sys.stderr)
        return 2

    if resp.status_code != 200:
        print(f"[ERROR] Сервер вернул {resp.status_code}: {resp.text}", file=sys.stderr)
        return 2

    data = resp.json()
    bot_id = data.get("botId")
    secret = data.get("secret")
    if not bot_id or not secret:
        print("[ERROR] Некорректный ответ сервера", file=sys.stderr)
        return 2

    # Сохраняем
    set_discord_token(discord_token)
    set_agent_secret(secret)

    config.bot_id = bot_id
    config.save()

    print(f"[OK] Привязка выполнена. bot_id={bot_id}")
    print("Фоновая служба подключит бота автоматически.")
    print("Если служба не установлена, запустите: python -m agent")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    purge_all()
    config = LocalConfig.load()
    config.bot_id = None
    config.save()
    print("[OK] Все секреты удалены, бот отвязан")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = env_override(LocalConfig.load())
    print(f"agent version:   {__version__}")
    print(f"server:          {config.server_url}")
    print(f"ws url:          {config.ws_url}")
    print(f"bot_id:          {config.bot_id or 'not paired'}")
    print(f"discord token:   {'saved' if get_discord_token() else 'missing'}")
    print(f"agent secret:    {'saved' if get_agent_secret() else 'missing'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = env_override(LocalConfig.load())
    if not config.bot_id or not get_discord_token() or not get_agent_secret():
        print("[ERROR] Агент не привязан. Сначала выполните: python -m agent pair", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    from .runtime import run
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        print("\nОстановлено пользователем")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    async def run_service() -> None:
        from .runtime import run

        runtime_task: asyncio.Task[None] | None = None

        try:
            while runtime_task is None:
                config = env_override(LocalConfig.load())
                if config.bot_id and get_discord_token() and get_agent_secret():
                    runtime_task = asyncio.create_task(run(config), name="discord-agent")
                    break
                await asyncio.sleep(2)

            await runtime_task
        finally:
            if runtime_task is not None:
                runtime_task.cancel()
                try:
                    await runtime_task
                except asyncio.CancelledError:
                    pass

    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="discord-panel-agent")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")

    p_pair = sub.add_parser("pair", help="Привязать агента к боту")
    p_pair.add_argument("--code", help="Pairing code (иначе спросит)")

    sub.add_parser("reset", help="Стереть секреты и отвязать")
    sub.add_parser("status", help="Показать состояние")
    sub.add_parser("run", help="Запустить (по умолчанию)")
    sub.add_parser("serve", help="Ожидать pairing и запустить Discord-агента")

    args = parser.parse_args()
    cmd = args.cmd or "run"

    if cmd == "pair":
        return asyncio.run(cmd_pair(args))
    if cmd == "reset":
        return cmd_reset(args)
    if cmd == "status":
        return cmd_status(args)
    if cmd == "run":
        return cmd_run(args)
    if cmd == "serve":
        return cmd_serve(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())