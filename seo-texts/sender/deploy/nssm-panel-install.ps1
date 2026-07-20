# nssm-panel-install.ps1 — установка службы Windows для веб-панели «Руспром-сендер».
#
# На Windows-сервере (как движок в RUNBOOK-DEPLOY §3.1) панель проще запускать
# ОДНИМ процессом в режиме «сайт+API» (serve-api --static-dir): uvicorn раздаёт и
# статику SPA, и API под /api. Затем публикуем через IIS+ARR/Cloudflare (как
# unsub-сервер, §4) — обратный прокси на 127.0.0.1:PANEL_PORT для TLS.
#
# Предварительно (один раз):
#   1) собрать SPA:   cd C:\sender\seo-texts\sender\web ; npm ci ; npm run build
#   2) поставить зависимости API в venv:  pip install -r seo-texts\sender\requirements-dev.txt
#   3) создать owner'а панели:  python -m sender user-create --username kirill --role owner
#      (пароль — через env SENDER_NEW_USER_PASSWORD, НЕ в командной строке)
#
# Запуск от имени администратора:  powershell -ExecutionPolicy Bypass -File nssm-panel-install.ps1

$ErrorActionPreference = "Stop"

# --- ПОДГОНИТЕ ПОД СВОЮ РАСКЛАДКУ ---
$Nssm       = "C:\nssm\win64\nssm.exe"
$Python     = (Get-Command python).Source                       # или явный путь к python.exe
$Root       = "C:\sender\seo-texts"                             # каталог с пакетом sender/
$Config     = "C:\sender\sender.yaml"
$StaticDir  = "C:\sender\seo-texts\sender\web\dist"             # собранный SPA
$Port       = "8090"
$Secret     = $env:UNSUB_SIGNING_SECRET                         # общий секрет с движком
$LogDir     = "C:\sender\logs"
$Service    = "RuspromSenderPanel"
# ------------------------------------

if (-not (Test-Path $StaticDir)) {
    throw "Не найден собранный SPA: $StaticDir — сначала 'npm run build' в sender\web"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# создать/переустановить службу
& $Nssm stop    $Service 2>$null
& $Nssm remove  $Service confirm 2>$null
& $Nssm install $Service $Python "-m" "sender" "serve-api" "--host" "127.0.0.1" "--port" $Port "--static-dir" $StaticDir

& $Nssm set $Service AppDirectory   $Root
& $Nssm set $Service DisplayName    "Rusprom Sender Panel"
& $Nssm set $Service Description    "Веб-панель рассылки (сайт+API, uvicorn)"
& $Nssm set $Service Start          SERVICE_AUTO_START

# окружение: путь к конфигу + секрет подписи (+ пароли ящиков, если панель их читает)
& $Nssm set $Service AppEnvironmentExtra "SENDER_CONFIG=$Config" "UNSUB_SIGNING_SECRET=$Secret"

# логи с ротацией (как у остальных служб, §3.1)
& $Nssm set $Service AppStdout          "$LogDir\panel.log"
& $Nssm set $Service AppStderr          "$LogDir\panel.err.log"
& $Nssm set $Service AppRotateFiles     1
& $Nssm set $Service AppRotateOnline    1
& $Nssm set $Service AppRotateBytes     10485760

& $Nssm start $Service
& $Nssm status $Service

Write-Host ""
Write-Host "Готово. Панель слушает http://127.0.0.1:$Port (сайт+API одним процессом)."
Write-Host "Дальше: опубликуйте её через IIS+ARR/Cloudflare на HTTPS (RUNBOOK-DEPLOY §4, §7),"
Write-Host "ограничьте доступ офисной сетью/VPN — это внутренний инструмент."
