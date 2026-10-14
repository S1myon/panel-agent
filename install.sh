#!/usr/bin/env bash
set -euo pipefail
REPO="S1myon/panel-agent"
VERSION="v0.1.0"
URL="https://github.com/$REPO/releases/download/$VERSION/panel-agent"

echo "→ Скачиваю агент..."
sudo curl -fsSL "$URL" -o /usr/local/bin/panel-agent
sudo chmod +x /usr/local/bin/panel-agent

echo "→ Регистрирую сервис..."
sudo tee /etc/systemd/system/panel-agent.service > /dev/null <<EOF
[Unit]
Description=Discord Panel Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/panel-agent run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now panel-agent
echo "✓ Готово."
