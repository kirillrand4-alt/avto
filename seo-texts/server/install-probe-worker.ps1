# Установка работника проверки адресов на отдельный сервер (Windows).
#
# Запуск на сервере 89.22.169.2 (RDP -> PowerShell от администратора),
# ОДНОЙ командой:
#
#   powershell -ExecutionPolicy Bypass -File C:\install-probe-worker.ps1
#
# Что делает: ставит Python (если нет), забирает работника с дропа, прописывает
# настройки, создаёт задачу в планировщике (каждые 10 минут) и делает первый
# пробный запуск. Ничего не отправляет: работник только спрашивает у почтовых
# серверов, существует ли ящик.
#
# Файл сохранён в UTF-8 С BOM: PowerShell 5.1 иначе ломается на кириллице.

$ErrorActionPreference = 'Stop'
$Кор     = 'C:\probe'
$Питон   = 'C:\Program Files\Python312\python.exe'
$Дроп    = 'https://parsercompressor.online/drop'
$Токен   = $env:DROP_TOKEN
$Хело    = 'probe.compressor-pro-systems.ru'
$ОтКого  = 'postmaster@compressor-pro-systems.ru'

function Скажи($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

if (-not $Токен) {
    $Токен = Read-Host "Вставьте DROP_TOKEN (он есть в C:\sender\server\runner-secrets.env на основном сервере)"
}
if (-not $Токен) { throw "без DROP_TOKEN работник не сможет забрать задание" }

New-Item -ItemType Directory -Path $Кор -Force | Out-Null

# --- 1. Python ---
if (-not (Test-Path $Питон)) {
    $найден = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($найден) {
        $Питон = $найден
        Скажи "Python уже стоит: $Питон"
    } else {
        Скажи "ставлю Python 3.12 (это занимает пару минут)"
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

# --- 1б. dnspython: без него MX ищет nslookup, с ним — надёжнее и быстрее ---
try {
    & $Питон -m pip install --quiet --disable-pip-version-check dnspython 2>&1 | Out-Null
    Скажи "dnspython поставлен"
} catch {
    Скажи "dnspython не поставился — MX будет искаться через nslookup, это тоже работает"
}

# --- 2. Работник с дропа ---
Скажи "качаю работника с дропа"
$заг = @{ 'X-Drop-Token' = $Токен }
Invoke-WebRequest -Uri "$Дроп/probe_worker.py" -Headers $заг `
                  -OutFile (Join-Path $Кор 'probe_worker.py') -UseBasicParsing
$размер = (Get-Item (Join-Path $Кор 'probe_worker.py')).Length
if ($размер -lt 2000) { throw "работник скачался битым ($размер байт)" }
Скажи "работник на месте: $размер байт"

# --- 3. Настройки (машинные переменные, видны планировщику) ---
[Environment]::SetEnvironmentVariable('DROP_URL',        $Дроп,   'Machine')
[Environment]::SetEnvironmentVariable('DROP_TOKEN',      $Токен,  'Machine')
[Environment]::SetEnvironmentVariable('PROBE_HELO',      $Хело,   'Machine')
[Environment]::SetEnvironmentVariable('PROBE_MAIL_FROM', $ОтКого, 'Machine')
Скажи "настройки прописаны"

# --- 4. Задача в планировщике: каждые 10 минут ---
$имяЗадачи = 'ProbeWorker'
# schtasks пишет «задача не найдена» в поток ошибок, а при $ErrorActionPreference='Stop'
# PowerShell считает это падением всего скрипта. Поэтому на время работы с
# планировщиком переходим на «продолжай» и смотрим на код возврата, а не на stderr.
$преж = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

# Путь к Python лежит в «Program Files» — с пробелом. Вместо того чтобы
# протаскивать кавычки через PowerShell, cmd и планировщик (там они теряются
# по-разному), кладём команду в .cmd-обёртку: задача получает ОДИН путь без
# пробелов и кавычек, и ломаться нечему.
$обёртка = Join-Path $Кор 'run-probe.cmd'
@"
@echo off
"$Питон" "$Кор\probe_worker.py" --limit 60 --pause 3
"@ | Set-Content -Path $обёртка -Encoding ASCII

cmd /c "schtasks /Query /TN $имяЗадачи >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    cmd /c "schtasks /Delete /TN $имяЗадачи /F >nul 2>&1" | Out-Null
    Скажи "старая задача удалена"
}
cmd /c "schtasks /Create /TN $имяЗадачи /TR $обёртка /SC MINUTE /MO 10 /RU SYSTEM /RL HIGHEST /F >nul 2>&1"
$кодЗадачи = $LASTEXITCODE
$ErrorActionPreference = $преж
if ($кодЗадачи -ne 0) {
    Скажи "ЗАДАЧА НЕ СОЗДАЛАСЬ (код $кодЗадачи). Работник установлен и работает вручную:"
    Скажи "   & '$Питон' '$Кор\probe_worker.py' --demon 600"
} else {
    Скажи "задача создана: каждые 10 минут"
}

# --- 5. Пробный запуск ---
Скажи "пробный запуск (проверю связь и один-два адреса)"
$env:DROP_URL = $Дроп; $env:DROP_TOKEN = $Токен
$env:PROBE_HELO = $Хело; $env:PROBE_MAIL_FROM = $ОтКого
& $Питон (Join-Path $Кор 'probe_worker.py') --limit 3 --pause 2
Скажи "готово. Дальше работник ходит сам, результаты кладёт на дроп."
