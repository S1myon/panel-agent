from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from agent.cli import cmd_pair
from agent.config import LocalConfig


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, str]):
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self) -> dict[str, str]:
        return self._data


class FakeHttpClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> FakeHttpClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return FakeResponse(200, {"id": "12345678901234567"})

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        return FakeResponse(200, {"botId": "bot-id", "secret": "agent-secret"})


class PairCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_is_validated_with_discord_and_never_sent_to_panel(self) -> None:
        client = FakeHttpClient()
        config = LocalConfig(server_url="https://panel.example.test")
        with (
            patch("agent.cli.env_override", return_value=config),
            patch("agent.cli.LocalConfig.load", return_value=config),
            patch("agent.cli._prompt", return_value="ABCD-EFGH"),
            patch("agent.cli._prompt_hidden", return_value="private-discord-token"),
            patch("agent.cli.httpx.AsyncClient", return_value=client),
            patch("agent.cli.set_discord_token") as save_token,
            patch("agent.cli.set_agent_secret") as save_secret,
            patch.object(config, "save") as save_config,
            patch("builtins.print"),
        ):
            result = await cmd_pair(argparse.Namespace(code=None))

        self.assertEqual(result, 0)
        self.assertEqual(client.requests[0][0], "https://discord.com/api/v10/users/@me")
        panel_url, panel_request = client.requests[1]
        self.assertEqual(panel_url, "https://panel.example.test/agent/pair")
        self.assertEqual(
            panel_request["json"],
            {"code": "ABCD-EFGH", "label": "cli", "discordAppId": "12345678901234567"},
        )
        self.assertNotIn("private-discord-token", str(panel_request))
        save_token.assert_called_once_with("private-discord-token")
        save_secret.assert_called_once_with("agent-secret")
        save_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
