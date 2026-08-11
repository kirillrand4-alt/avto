# Починка раннера на проверочном VPS + сторож, чтобы это не повторилось.
#
# Запуск на VPS (RDP -> PowerShell от администратора), ОДНОЙ командой:
#
#   powershell -ExecutionPolicy Bypass -File C:\remont-vps.ps1
#
# Что случилось 11.08: машина жива (пингуется, RDP открыт), а раннер молчал
# 18 часов. Задача VpsRunner стояла на ОДНОМ триггере — старт системы. Умер
# процесс — поднять его нечем до следующей перезагрузки, а её никто не делает.
#
# Что делает скрипт: обновляет раннер с дропа, добавляет задачу-СТОРОЖ раз в
# пять минут и запускает раннер сейчас. Второй экземпляр не появится: раннер
# держит порт-замок и лишний запуск сам выходит.
#
# Ключи берутся из C:\probe\runner-secrets.env — вводить ничего не нужно.
# Файл сохранён в UTF-8 С BOM: PowerShell 5.1 иначе ломается на кириллице.

$ErrorActionPreference = 'Stop'
$Root   = 'C:\probe'
$Python = 'C:\Program Files\Python312\python.exe'

function Say($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

if (-not (Test-Path $Python)) {
    $Found = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $Found) { throw "Python не найден — запустите install-vps-runner.ps1" }
    $Python = $Found
}

$SecretsFile = Join-Path $Root 'runner-secrets.env'
if (-not (Test-Path $SecretsFile)) { throw "нет $SecretsFile — запустите install-vps-runner.ps1" }
$Secrets = @{}
foreach ($Line in Get-Content $SecretsFile) {
    if ($Line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $Secrets[$Matches[1]] = $Matches[2].Trim() }
}
$Drop  = $Secrets['DROP_URL']
$Token = $Secrets['DROP_TOKEN']
if (-not $Token) { throw "в $SecretsFile нет DROP_TOKEN" }
Say "ключи прочитаны из $SecretsFile"

# --- 1. Свежий раннер и работник проверки ---
$Headers = @{ 'X-Drop-Token' = $Token }
foreach ($Name in @('vps_runner.py', 'probe_worker.py')) {
    $Dest = Join-Path $Root $Name
    $Tmp  = "$Dest.new"
    Invoke-WebRequest -Uri "$Drop/$Name" -Headers $Headers -OutFile $Tmp -UseBasicParsing
    $Size = (Get-Item $Tmp).Length
    if ($Size -lt 2000) { Remove-Item $Tmp -Force; throw "$Name скачался битым ($Size байт)" }
    Move-Item $Tmp $Dest -Force
    Say "   $Name обновлён: $Size байт"
}

# --- 2. Обёртка (та же, что при установке) ---
$Wrapper = Join-Path $Root 'run-vps-runner.cmd'
@"
@echo off
cd /d "$Root"
"$Python" "$Root\vps_runner.py" --poll 20 --probe-every 600 --limit 60
"@ | Set-Content -Path $Wrapper -Encoding ASCII

# --- 3. Задачи: пуск при старте + СТОРОЖ раз в пять минут ---
$PrevEA = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

cmd /c "schtasks /Query /TN VpsRunner >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunner /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunner /TR $Wrapper /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
Say "задача VpsRunner пересоздана (старт системы)"

# Сторож. Запускается каждые 5 минут и просто зовёт ту же обёртку: если раннер
# жив, новый процесс упирается в занятый порт-замок и выходит за секунду.
cmd /c "schtasks /Query /TN VpsRunnerWatch >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunnerWatch /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunnerWatch /TR $Wrapper /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
$WatchCode = $LASTEXITCODE
if ($WatchCode -ne 0) {
    Say "СТОРОЖ НЕ СОЗДАЛСЯ (код $WatchCode) — раннер будет подниматься только при старте системы"
} else {
    Say "сторож VpsRunnerWatch создан: проверяет раннер каждые 5 минут"
}

# --- 4. Поднять сейчас ---
Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
    Say "нашёлся старый процесс python (PID $($_.Id)) — снимаю, чтобы замок был свободен"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
cmd /c "schtasks /Run /TN VpsRunner >nul 2>&1"

$Alive = $null
foreach ($i in 1..10) {
    Start-Sleep -Seconds 3
    $Alive = Get-Process -Name python -ErrorAction SilentlyContinue
    if ($Alive) { break }
}
$ErrorActionPreference = $PrevEA
if ($Alive) {
    Say "готово: раннер работает (PID $($Alive.Id -join ', ')). Дальше сам."
} else {
    Say "процесс за 30 секунд не появился. Покажите вывод: schtasks /Query /TN VpsRunner /FO LIST /V"
}
