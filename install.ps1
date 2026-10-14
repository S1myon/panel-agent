$ErrorActionPreference = "Stop"
REPO="S1myon/panel-agent"
$version = "v0.1.0"
$url = "https://github.com/$repo/releases/download/$version/panel-agent.exe"
$dest = "$env:LOCALAPPDATA\panel-agent"
$exe = "$dest\panel-agent.exe"

Write-Host "→ Скачиваю агент..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Invoke-WebRequest -Uri $url -OutFile $exe

Write-Host "→ Регистрирую задачу в планировщике..." -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute $exe -Argument "run"
$trigger = New-ScheduledTaskTrigger -AtLogon
Register-ScheduledTask -TaskName "DiscordPanelAgent" -Action $action -Trigger $trigger -Force | Out-Null
Start-ScheduledTask -TaskName "DiscordPanelAgent"

Write-Host "✓ Готово." -ForegroundColor Green
