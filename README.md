# Discord Panel Agent

The agent maintains the Discord Gateway connection and applies configuration from
the panel. Install it on the computer or VPS that should keep the bot online.

## Install

Run `python install.py` in this directory. The installer detects Linux, Windows,
or macOS; asks whether this is a VPS or personal computer; asks for the panel API
URL; installs dependencies; and configures a background service. Python 3.11 or
later is required.

Create a one-time pairing code on the bot page in the panel. In CMD/terminal on
the agent host, run the pairing command printed by the installer. It prompts for
the code and then for the Discord bot token using hidden input. The token is
stored only on the agent host; the pairing code and public Application ID are
sent to the panel API. The agent reads the Application ID from Discord while
validating the token, so it does not need to be entered manually. Once pairing
succeeds, the background service starts the Discord connection.

## Secret storage

The Discord token and agent credential are stored on the agent host using its
system keyring when available. On headless Linux systems without a keyring, the
agent uses a user-only permissions file. Protect the VPS account and disk; the
agent host must retain the token to reconnect to Discord after a restart.

## Discord application

The Application ID is public and identifies the Discord application; the agent
detects it from the token during pairing. The Public Key is not used for this
connection flow. Enable the privileged Gateway intents required by enabled
modules in the Discord Developer Portal.
