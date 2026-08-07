# Установка раннера на проверочный VPS (89.22.169.2, Windows Server 2022).
#
# Запуск на сервере (RDP -> PowerShell от администратора), ОДНОЙ командой:
#
#   powershell -ExecutionPolicy Bypass -File C:\install-vps-runner.ps1
#
# Что делает: ставит Python и dnspython (если нет), забирает раннер и работника
# проверки адресов с дропа, прописывает ключи, регистрирует раннер как ЗАДАЧУ
# ПРИ СТАРТЕ СИСТЕМЫ и запускает прямо сейчас.
#
# Раннер сам гоняет проверку адресов каждые 10 минут, поэтому ОТДЕЛЬНАЯ задача
# ProbeWorker больше не нужна — если она осталась от прошлой установки, скрипт
# её удалит, чтобы две копии не проверяли одно и то же с одного IP.
#
# Файл сохранён в UTF-8 С BOM: PowerShell 5.1 иначе ломается на кириллице.

$ErrorActionPreference = 'Stop'
$Root    = 'C:\probe'
$Python  = 'C:\Program Files\Python312\python.exe'
$Drop   = 'https://parsercompressor.online/drop'
$Helo   = 'probe.compressor-pro-systems.ru'
$MailFrom = 'postmaster@compressor-pro-systems.ru'

function Say($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

$Token = $env:DROP_TOKEN
if (-not $Token) { $Token = Read-Host "Вставьте DROP_TOKEN" }
if (-not $Token) { throw "без DROP_TOKEN раннер не сможет ходить на дроп" }
$Secret = $env:JOB_SECRET
if (-not $Secret) { $Secret = Read-Host "Вставьте JOB_SECRET (подпись заданий; Enter — без подписи)" }

New-Item -ItemType Directory -Path $Root -Force | Out-Null

# --- 1. Python ---
if (-not (Test-Path $Python)) {
    $Found = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($Found) {
        $Python = $Found
        Say "Python уже стоит: $Python"
    } else {
        Say "ставлю Python 3.12 (пара минут)"
        $Inst = Join-Path $env:TEMP 'python-setup.exe'
        Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' `
                          -OutFile $Inst -UseBasicParsing
        Start-Process -FilePath $Inst -Wait -ArgumentList `
            '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
        if (-not (Test-Path $Python)) { throw "Python не установился, поставьте вручную с python.org" }
        Say "Python установлен"
    }
} else {
    Say "Python уже стоит"
}

try {
    & $Python -m pip install --quiet --disable-pip-version-check dnspython 2>&1 | Out-Null
    Say "dnspython поставлен"
} catch {
    Say "dnspython не поставился — MX будет искаться через nslookup, это тоже работает"
}

# --- 2. Файлы с дропа ---
$Headers = @{ 'X-Drop-Token' = $Token }
foreach ($Name in @('vps_runner.py', 'probe_worker.py')) {
    Say "качаю $Name"
    Invoke-WebRequest -Uri "$Drop/$Name" -Headers $Headers `
                      -OutFile (Join-Path $Root $Name) -UseBasicParsing
    $Size = (Get-Item (Join-Path $Root $Name)).Length
    if ($Size -lt 2000) { throw "$Name скачался битым ($Size байт)" }
    Say "   $Name на месте: $Size байт"
}

# --- 3. Ключи в файл рядом со скриптом (раннер читает его сам) ---
$SecretsFile = Join-Path $Root 'runner-secrets.env'
@"
DROP_URL=$Drop
DROP_TOKEN=$Token
JOB_SECRET=$Secret
PROBE_HELO=$Helo
PROBE_MAIL_FROM=$MailFrom
"@ | Set-Content -Path $SecretsFile -Encoding UTF8
Say "ключи записаны в $SecretsFile"

# --- 4. Обёртка и задача при старте системы ---
$PrevEA = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

# Путь к Python лежит в «Program Files» — с пробелом. Кавычки через PowerShell,
# cmd и планировщик теряются по-разному, поэтому команда живёт в .cmd-файле:
# задача получает один путь и ломаться нечему.
$Wrapper = Join-Path $Root 'run-vps-runner.cmd'
@"
@echo off
cd /d "$Root"
"$Python" "$Root\vps_runner.py" --poll 20 --probe-every 600 --limit 60
"@ | Set-Content -Path $Wrapper -Encoding ASCII

# Старая задача проверки больше не нужна: раннер делает то же сам.
cmd /c "schtasks /Query /TN ProbeWorker >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    cmd /c "schtasks /Delete /TN ProbeWorker /F >nul 2>&1" | Out-Null
    Say "старая задача ProbeWorker удалена — раннер проверяет адреса сам"
}
cmd /c "schtasks /Query /TN VpsRunner >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunner /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunner /TR $Wrapper /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
$TaskCode = $LASTEXITCODE
$ErrorActionPreference = $PrevEA
if ($TaskCode -ne 0) {
    Say "ЗАДАЧА НЕ СОЗДАЛАСЬ (код $TaskCode) — раннер можно держать вручную:"
    Say "   & '$Python' '$Root\vps_runner.py'"
} else {
    Say "задача VpsRunner создана: поднимается при старте системы"
}

# --- 5. Проверка: один круг на месте, затем запуск в фоне ---
Say "пробный круг (свяжусь с дропом и проверю пару адресов)"
& $Python (Join-Path $Root 'vps_runner.py') --once --limit 3

$ErrorActionPreference = 'Continue'
cmd /c "schtasks /Run /TN VpsRunner >nul 2>&1"
Start-Sleep -Seconds 3
$Alive = Get-Process -Name python -ErrorAction SilentlyContinue
if ($Alive) {
    Say "готово: раннер работает (PID $($Alive.Id -join ', ')). Дальше сам."
} else {
    Say "задача создана, но процесс не виден. Запустите вручную:"
    Say "   schtasks /Run /TN VpsRunner"
}
