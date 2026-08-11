# Починка раннера на проверочном VPS + сторож, который действительно работает.
#
# Запуск на VPS (RDP -> PowerShell от администратора), ОДНОЙ командой:
#
#   powershell -ExecutionPolicy Bypass -File C:\remont-vps.ps1
#
# История. 11.08 раннер молчал 18 часов при живой машине: задача VpsRunner
# стояла на одном триггере — старт системы. Добавили сторожа раз в пять минут,
# он звал ТУ ЖЕ обёртку, что и основная задача. Через два часа раннер снова
# умер, и сторож его не поднял.
#
# Почему. Обёртка держит python синхронно: пока раннер жив, экземпляр задачи
# планировщика тоже «выполняется», а планировщик по умолчанию НЕ запускает
# второй экземпляр. Сторож, поднявший раннер, залипает в этом состоянии
# навсегда — и следующие срабатывания просто пропускаются.
#
# Как теперь. Сторож запускает раннер ОТЦЕПЛЁННО (Start-Process) и сразу
# выходит: его экземпляр живёт секунду и не мешает следующим. Двух раннеров не
# будет — второй упирается в занятый порт-замок и выходит сам.
#
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

# --- 0. Что было: состояние задач ДО починки, чтобы понять причину ---------- #
$PrevEA = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
Say "--- состояние задач до починки ---"
foreach ($T in @('VpsRunner', 'VpsRunnerWatch')) {
    $Info = cmd /c "schtasks /Query /TN $T /FO LIST /V 2>&1"
    $Nuzhno = $Info | Select-String -Pattern 'Состояние|Status|Последн|Last Run|Результат|Result|Следующ|Next Run'
    if ($Nuzhno) { Say "$T :"; $Nuzhno | ForEach-Object { Write-Host ("    " + $_.ToString().Trim()) } }
    else { Say "$T : задачи нет" }
}
$Idut = Get-Process -Name python -ErrorAction SilentlyContinue
Say ("процессов python сейчас: " + $(if ($Idut) { ($Idut.Id -join ', ') } else { 'ни одного' }))

# --- 1. Свежий раннер и работник проверки ----------------------------------- #
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

# --- 2. Две обёртки: рабочая и сторожевая ----------------------------------- #
# Рабочая держит раннер (её зовёт задача при старте системы).
$Wrapper = Join-Path $Root 'run-vps-runner.cmd'
@"
@echo off
cd /d "$Root"
"$Python" "$Root\vps_runner.py" --poll 20 --probe-every 300 --limit 120
"@ | Set-Content -Path $Wrapper -Encoding ASCII

# Сторожевая ЗАПУСКАЕТ и сразу выходит. Ключевое отличие от прошлой редакции:
# экземпляр задачи не живёт вместе с раннером и не блокирует свои же будущие
# срабатывания.
$Watcher = Join-Path $Root 'watch-vps-runner.cmd'
@"
@echo off
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '$Python' -ArgumentList '$Root\vps_runner.py','--poll','20','--probe-every','300','--limit','120' -WorkingDirectory '$Root' -WindowStyle Hidden"
"@ | Set-Content -Path $Watcher -Encoding ASCII
Say "обёртки записаны: рабочая и сторожевая"

# --- 3. Задачи -------------------------------------------------------------- #
cmd /c "schtasks /Query /TN VpsRunner >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunner /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunner /TR $Watcher /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
Say "задача VpsRunner пересоздана (старт системы, запуск отцеплённо)"

cmd /c "schtasks /Query /TN VpsRunnerWatch >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunnerWatch /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunnerWatch /TR $Watcher /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Say "СТОРОЖ НЕ СОЗДАЛСЯ (код $LASTEXITCODE)" }
else { Say "сторож VpsRunnerWatch пересоздан: проверяет раннер каждые 5 минут" }

# --- 4. Поднять сейчас ------------------------------------------------------ #
Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
    Say "снимаю старый python (PID $($_.Id)), чтобы замок был свободен"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
cmd /c "schtasks /Run /TN VpsRunnerWatch >nul 2>&1"

$Alive = $null
foreach ($i in 1..12) {
    Start-Sleep -Seconds 3
    $Alive = Get-Process -Name python -ErrorAction SilentlyContinue
    if ($Alive) { break }
}
$ErrorActionPreference = $PrevEA
if ($Alive) {
    Say "готово: раннер работает (PID $($Alive.Id -join ', ')). Дальше сам."
    Say "проверка сторожа: экземпляр задачи должен УЖЕ завершиться —"
    cmd /c "schtasks /Query /TN VpsRunnerWatch /FO LIST 2>&1" | Select-String -Pattern 'Состояние|Status' | ForEach-Object { Write-Host ("    " + $_.ToString().Trim()) }
} else {
    Say "процесс за 36 секунд не появился. Покажите вывод:"
    Say "   schtasks /Query /TN VpsRunnerWatch /FO LIST /V"
}
