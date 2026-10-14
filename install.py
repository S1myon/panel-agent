"""Install the agent as a background service on the current operating system."""
from __future__ import annotations

import ctypes
import getpass
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True)


def prompt(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def validate_panel_url(value: str) -> str:
    parsed = urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not local_http:
        raise ValueError("Panel API must use HTTPS, except on localhost.")
    if not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Enter a valid panel API base URL without query or fragment.")
    return value.rstrip("/")


def derive_ws_url(server_url: str) -> str:
    parsed = urlsplit(server_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, "/ws/agent", "", ""))


def write_config() -> None:
    sys.path.insert(0, str(ROOT))
    from agent.config import LocalConfig

    server_url = validate_panel_url(prompt("Panel API URL", "https://panel.example.com"))

    config = LocalConfig.load()
    config.server_url = server_url
    config.ws_url = derive_ws_url(server_url)
    config.save()


def install_windows(target: str) -> None:
    runner = ROOT / "run-agent.cmd"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    profile = Path.home()
    runner.write_text(
        f'@echo off\r\n'
        f'set "USERPROFILE={profile}"\r\n'
        f'set "APPDATA={profile / "AppData" / "Roaming"}"\r\n'
        f'set "LOCALAPPDATA={profile / "AppData" / "Local"}"\r\n'
        f'cd /d "{ROOT}"\r\n'
        f'"{VENV}\\Scripts\\python.exe" -m agent serve >> "{logs / "agent.log"}" 2>&1\r\n',
        encoding="utf-8",
    )
    if target == "vps":
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise RuntimeError("Run this installer as Administrator to register the VPS boot task.")
        schedule = "ONSTART"
        user = getpass.getuser()
    else:
        schedule = "ONLOGON"
        user = getpass.getuser()
    task_args = [
        "schtasks",
        "/Create",
        "/TN",
        "DiscordPanelAgent",
        "/SC",
        schedule,
        "/RU",
        user,
    ]
    if target == "vps":
        task_args.extend(["/RP", "*"])
    task_args.extend(["/TR", str(runner), "/F"])
    run(*task_args)
    run("schtasks", "/Run", "/TN", "DiscordPanelAgent")
    start_description = "Windows startup" if target == "vps" else "Windows sign-in"
    print(f"Installed to Task Scheduler; the agent starts at {start_description}.")


def install_macos() -> None:
    label = "com.discordpanel.agent"
    agent_dir = Path.home() / "Library" / "LaunchAgents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / "Library" / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    plist_path = agent_dir / f"{label}.plist"
    plist = {
        "Label": label,
        "ProgramArguments": [str(VENV / "bin" / "python"), "-m", "agent", "serve"],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(logs / "discord-panel-agent.log"),
        "StandardErrorPath": str(logs / "discord-panel-agent-error.log"),
    }
    plist_path.write_bytes(plistlib.dumps(plist))
    run("launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist_path), check=False)
    run("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}")
    print(f"Installed LaunchAgent: {plist_path}")


def install_linux(target: str) -> None:
    systemctl = run("systemctl", "--user", "--version", check=False)
    if systemctl.returncode != 0:
        raise RuntimeError("systemd user services are not available on this Linux host.")
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    unit = service_dir / "discord-panel-agent.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Discord Panel Agent\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={ROOT}\n"
        f"ExecStart={VENV / 'bin' / 'python'} -m agent serve\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "NoNewPrivileges=true\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "--now", "discord-panel-agent.service")
    if target == "vps":
        if shutil.which("loginctl") is None:
            raise RuntimeError("loginctl is required to keep a VPS user service running after logout.")
        user = getpass.getuser()
        if shutil.which("sudo"):
            run("sudo", "loginctl", "enable-linger", user)
        else:
            run("loginctl", "enable-linger", user)
    print(f"Installed systemd user service: {unit}")


def main() -> int:
    system = platform.system()
    if system not in {"Windows", "Linux", "Darwin"}:
        print(f"Unsupported operating system: {system}", file=sys.stderr)
        return 1
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1

    print(f"Detected {system}. Choose where the agent will run; no OS selection is needed.")
    target = prompt("Deployment target (VPS or PC)", "PC").lower()
    if target not in {"vps", "pc"}:
        print("Choose VPS or PC.", file=sys.stderr)
        return 1
    try:
        run(sys.executable, "-m", "venv", str(VENV))
        python = VENV / ("Scripts/python.exe" if system == "Windows" else "bin/python")
        run(str(python), "-m", "pip", "install", "--upgrade", "pip")
        run(str(python), "-m", "pip", "install", "-e", str(ROOT))
        write_config()
        if system == "Windows":
            install_windows(target)
        elif system == "Darwin":
            install_macos()
        else:
            install_linux(target)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 1

    print("Pair the agent from CMD/terminal using the one-time code shown in the panel.")
    if system == "Windows":
        print(f'  cd /d "{ROOT}"')
        print('  ".venv\\Scripts\\python.exe" -m agent pair')
    else:
        print(f'  cd "{ROOT}"')
        print('  ./.venv/bin/python -m agent pair')
    print("The command prompts for the pairing code and hidden Discord bot token.")
    print("The background service starts the Discord connection after pairing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
