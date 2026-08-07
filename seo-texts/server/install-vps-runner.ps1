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
$Кор    = 'C:\probe'
$Питон  = 'C:\Program Files\Python312\python.exe'
$Дроп   = 'https://parsercompressor.online/drop'
$Хело   = 'probe.compressor-pro-systems.ru'
$ОтКого = 'postmaster@compressor-pro-systems.ru'

function Скажи($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

$Токен = $env:DROP_TOKEN
if (-not $Токен) { $Токен = Read-Host "Вставьте DROP_TOKEN" }
if (-not $Токен) { throw "без DROP_TOKEN раннер не сможет ходить на дроп" }
$Секрет = $env:JOB_SECRET
if (-not $Секрет) { $Секрет = Read-Host "Вставьте JOB_SECRET (подпись заданий; Enter — без подписи)" }

New-Item -ItemType Directory -Path $Кор -Force | Out-Null

# --- 1. Python ---
if (-not (Test-Path $Питон)) {
    $найден = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($найден) {
        $Питон = $найден
        Скажи "Python уже стоит: $Питон"
    } else {
        Скажи "ставлю Python 3.12 (пара минут)"
        $инст = Join-Path $env:TEMP 'python-setup.exe'
        Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' `
                          -OutFile $инст -UseBasicParsing
        Start-Process -FilePath $инст -Wait -ArgumentList `
            '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
        if (-not (Test-Path $Питон)) { throw "Python не установился, поставьте вручную с python.org" }
        Скажи "Python установлен"
    }
} else {
    Скажи "Python уже стоит"
}

try {
    & $Питон -m pip install --quiet --disable-pip-version-check dnspython 2>&1 | Out-Null
    Скажи "dnspython поставлен"
} catch {
    Скажи "dnspython не поставился — MX будет искаться через nslookup, это тоже работает"
}

# --- 2. Файлы с дропа ---
$заг = @{ 'X-Drop-Token' = $Токен }
foreach ($имя in @('vps_runner.py', 'probe_worker.py')) {
    Скажи "качаю $имя"
    Invoke-WebRequest -Uri "$Дроп/$имя" -Headers $заг `
                      -OutFile (Join-Path $Кор $имя) -UseBasicParsing
    $размер = (Get-Item (Join-Path $Кор $имя)).Length
    if ($размер -lt 2000) { throw "$имя скачался битым ($размер байт)" }
    Скажи "   $имя на месте: $размер байт"
}

# --- 3. Ключи в файл рядом со скриптом (раннер читает его сам) ---
$секреты = Join-Path $Кор 'runner-secrets.env'
@"
DROP_URL=$Дроп
DROP_TOKEN=$Токен
JOB_SECRET=$Секрет
PROBE_HELO=$Хело
PROBE_MAIL_FROM=$ОтКого
"@ | Set-Content -Path $секреты -Encoding UTF8
Скажи "ключи записаны в $секреты"

# --- 4. Обёртка и задача при старте системы ---
$преж = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

# Путь к Python лежит в «Program Files» — с пробелом. Кавычки через PowerShell,
# cmd и планировщик теряются по-разному, поэтому команда живёт в .cmd-файле:
# задача получает один путь и ломаться нечему.
$обёртка = Join-Path $Кор 'run-vps-runner.cmd'
@"
@echo off
cd /d "$Кор"
"$Питон" "$Кор\vps_runner.py" --poll 20 --probe-every 600 --limit 60
"@ | Set-Content -Path $обёртка -Encoding ASCII

# Старая задача проверки больше не нужна: раннер делает то же сам.
cmd /c "schtasks /Query /TN ProbeWorker >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    cmd /c "schtasks /Delete /TN ProbeWorker /F >nul 2>&1" | Out-Null
    Скажи "старая задача ProbeWorker удалена — раннер проверяет адреса сам"
}
cmd /c "schtasks /Query /TN VpsRunner >nul 2>&1"
if ($LASTEXITCODE -eq 0) { cmd /c "schtasks /Delete /TN VpsRunner /F >nul 2>&1" | Out-Null }
cmd /c "schtasks /Create /TN VpsRunner /TR $обёртка /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
$кодЗадачи = $LASTEXITCODE
$ErrorActionPreference = $преж
if ($кодЗадачи -ne 0) {
    Скажи "ЗАДАЧА НЕ СОЗДАЛАСЬ (код $кодЗадачи) — раннер можно держать вручную:"
    Скажи "   & '$Питон' '$Кор\vps_runner.py'"
} else {
    Скажи "задача VpsRunner создана: поднимается при старте системы"
}

# --- 5. Проверка: один круг на месте, затем запуск в фоне ---
Скажи "пробный круг (свяжусь с дропом и проверю пару адресов)"
& $Питон (Join-Path $Кор 'vps_runner.py') --once --limit 3

$ErrorActionPreference = 'Continue'
cmd /c "schtasks /Run /TN VpsRunner >nul 2>&1"
Start-Sleep -Seconds 3
$живой = Get-Process -Name python -ErrorAction SilentlyContinue
if ($живой) {
    Скажи "готово: раннер работает (PID $($живой.Id -join ', ')). Дальше сам."
} else {
    Скажи "задача создана, но процесс не виден. Запустите вручную:"
    Скажи "   schtasks /Run /TN VpsRunner"
}
