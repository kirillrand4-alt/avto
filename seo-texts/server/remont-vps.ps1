# Починка раннера на проверочном VPS. Третья и, надеюсь, последняя редакция.
#
# Запуск на VPS (RDP -> PowerShell от администратора), ОДНОЙ командой:
#
#   powershell -ExecutionPolicy Bypass -File C:\remont-vps.ps1
#
# История трёх редакций, чтобы не наступить на то же в четвёртый раз.
#
# 1) Задача стояла на одном триггере — старт системы. Умер процесс — поднять
#    нечем. Добавили сторожа раз в пять минут, звавшего ту же обёртку.
# 2) Сторож не помогал. Я решил, что его экземпляр залипает вместе с python, и
#    переделал сторожа на отцеплённый запуск (Start-Process). Стало ХУЖЕ:
#    планировщик держит задачу в объекте задания и убивает всё её потомство,
#    когда экземпляр завершается. Отцеплённый python жил секунду после старта.
# 3) Настоящая причина первого простоя оказалась в самом раннере: порт-замок
#    считал любую ошибку bind доказательством живого соседа и выходил с нулём.
#    Это исправлено в vps_runner.py, который скрипт качает ниже.
#
# Как теперь. ОДНА задача с СИНХРОННОЙ обёрткой, повтор каждые пять минут.
# Пока раннер жив, экземпляр задачи «выполняется», и планировщик по умолчанию
# новый не запускает — задача сама себе сторож. Умер раннер — экземпляр
# завершился, и следующее срабатывание поднимает его. Никаких Start-Process и
# никакого отдельного сторожа: меньше деталей — меньше поводов сломаться.
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

$PrevEA = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

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

# --- 2. Одна обёртка, синхронная ------------------------------------------- #
$Wrapper = Join-Path $Root 'run-vps-runner.cmd'
@"
@echo off
cd /d "$Root"
"$Python" "$Root\vps_runner.py" --poll 20 --probe-every 300 --limit 120
"@ | Set-Content -Path $Wrapper -Encoding ASCII
Remove-Item (Join-Path $Root 'watch-vps-runner.cmd') -Force -ErrorAction SilentlyContinue
Say "обёртка записана (синхронная), отцеплённая удалена"

# --- 3. Одна задача, повтор каждые пять минут ------------------------------- #
foreach ($T in @('VpsRunnerWatch', 'VpsRunner', 'ProbeWorker')) {
    cmd /c "schtasks /Query /TN $T >nul 2>&1"
    if ($LASTEXITCODE -eq 0) {
        cmd /c "schtasks /Delete /TN $T /F >nul 2>&1" | Out-Null
        Say "удалена прежняя задача $T"
    }
}
# /RI 5 /DU 9999:59 — повтор каждые 5 минут «навсегда». Именно эта форма, а не
# /SC MINUTE: у последней срок повторения по умолчанию ограничен сутками.
cmd /c "schtasks /Create /TN VpsRunner /TR $Wrapper /SC DAILY /ST 00:00 /RI 5 /DU 9999:59 /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Say "ЗАДАЧА НЕ СОЗДАЛАСЬ (код $LASTEXITCODE)" }
else { Say "задача VpsRunner создана: раз в 5 минут, сама себе сторож" }

# --- 4. Поднять сейчас ------------------------------------------------------ #
Get-Process -Name python -ErrorAction SilentlyContinue | ForEach-Object {
    Say "снимаю старый python (PID $($_.Id))"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
cmd /c "schtasks /Run /TN VpsRunner >nul 2>&1"

$Alive = $null
foreach ($i in 1..12) {
    Start-Sleep -Seconds 3
    $Alive = Get-Process -Name python -ErrorAction SilentlyContinue
    if ($Alive) { break }
}
Say ("процессы python: " + $(if ($Alive) { ($Alive.Id -join ', ') } else { 'ни одного' }))

# Главная проверка новой схемы: задача обязана ОСТАТЬСЯ «выполняется», пока
# раннер жив. Если она «Готово» — значит python снова умер вместе с ней, и
# схема не работает; лучше увидеть это здесь, чем через два часа тишины.
Start-Sleep -Seconds 10
Say "состояние задачи (ожидаем «Выполняется»):"
cmd /c "schtasks /Query /TN VpsRunner /FO LIST 2>&1" | Select-String -Pattern 'Состояние|Status' | ForEach-Object { Write-Host ("    " + $_.ToString().Trim()) }
$Alive2 = Get-Process -Name python -ErrorAction SilentlyContinue
Say ("python через 10 секунд: " + $(if ($Alive2) { ($Alive2.Id -join ', ') } else { 'УМЕР' }))

# Собственный лог раннера — единственное место, где видно ПОЧЕМУ он умер.
# Планировщик показывает только «Готово», а это неотличимо от штатного конца.
$Log = Join-Path $Root 'runner.log'
Say "--- последние строки $Log ---"
if (Test-Path $Log) {
    Get-Content $Log -Tail 40 -Encoding UTF8 | ForEach-Object { Write-Host ("    " + $_) }
} else {
    Say "    лога нет — раннер не дошёл даже до первой строки"
}
$ErrorActionPreference = $PrevEA
