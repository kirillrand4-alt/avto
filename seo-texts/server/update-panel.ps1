# Обновление ПАНЕЛИ РАССЫЛЬЩИКА (SenderPanel) из дропа.
# Запуск на сервере владельца:
#   powershell -ExecutionPolicy Bypass -File C:\sender\update-panel.ps1
#
# Что делает: качает panel-update.zip с дропа -> бэкапит текущие sender\ и web\dist ->
# останавливает службу -> распаковывает -> запускает -> ПРОВЕРЯЕТ, что панель живая.
# Если проверка не прошла — САМ откатывает бэкап и поднимает старую версию.
#
# Важные грабли, уже оплаченные:
#  * 401 от панели/обзвона — это ШТАТНАЯ Basic-авторизация, а НЕ отказ. Проверка
#    живости считает успехом любой HTTP-ответ, кроме 5xx и обрыва связи.
#    (Инцидент: скрипт принял 401 за падение и откатил рабочую выкатку.)
#  * Службу надо стопать ДО Expand-Archive: иначе питон держит .pyd/.pyc и часть
#    файлов не перезапишется — получим полуобновлённый пакет.
#  * Файл сохранён в UTF-8 С BOM: PowerShell 5.1 читает .ps1 в системной кодировке
#    и без BOM ломается на кириллице прямо в парсере.

$ErrorActionPreference = 'Stop'
$Root    = 'C:\sender'
$Zip     = Join-Path $Root 'panel-update.zip'
$Stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup  = Join-Path $Root ("_bak-panel-" + $Stamp)
$Service = 'SenderPanel'
$Health  = 'http://127.0.0.1:8091/api/health'
$DropUrl = 'https://parsercompressor.online/drop/panel-update.zip'

function Say($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

function Test-PanelAlive {
    # Живой = ответил хоть что-то не-5xx. 401/403/404 = служба на ногах.
    try {
        $r = Invoke-WebRequest -Uri $Health -TimeoutSec 20 -UseBasicParsing
        return ($r.StatusCode -lt 500)
    } catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($resp -ne $null) { return ([int]$resp.StatusCode -lt 500) }
        return $false
    } catch { return $false }
}

# --- 1. Скачать пакет ---
$tok = (Select-String -Path 'C:\sender\server\runner-secrets.env' -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Say "качаю panel-update.zip с дропа"
Invoke-WebRequest -Uri $DropUrl -Headers @{'X-Drop-Token'=$tok} -OutFile $Zip
$size = (Get-Item $Zip).Length
if ($size -lt 10000) { throw "архив подозрительно мал ($size байт) — качать нечего, выкатку отменяю" }
Say ("скачан: " + [math]::Round($size/1KB) + " КБ")

# --- 2. Бэкап того, что перезапишем ---
Say "бэкап в $Backup"
New-Item -ItemType Directory -Path $Backup -Force | Out-Null
if (Test-Path (Join-Path $Root 'sender')) {
    Copy-Item (Join-Path $Root 'sender') $Backup -Recurse -Force
}
if (Test-Path (Join-Path $Root 'web\dist')) {
    New-Item -ItemType Directory -Path (Join-Path $Backup 'web') -Force | Out-Null
    Copy-Item (Join-Path $Root 'web\dist') (Join-Path $Backup 'web') -Recurse -Force
}

# --- 3. Стоп службы, распаковка, старт ---
Say "останавливаю $Service"
Stop-Service $Service -Force
Start-Sleep -Seconds 2
Say "распаковываю поверх $Root"
Expand-Archive -Path $Zip -DestinationPath $Root -Force
Say "запускаю $Service"
Start-Service $Service

# --- 4. Проверка живости с несколькими попытками (служба поднимается не мгновенно) ---
$ok = $false
foreach ($i in 1..10) {
    Start-Sleep -Seconds 3
    if (Test-PanelAlive) { $ok = $true; break }
    Say ("жду подъёма службы, попытка " + $i + "/10")
}

if ($ok) {
    Say "ГОТОВО: панель обновлена и отвечает"
    if (Test-Path (Join-Path $Root 'UPDATE-MANIFEST.txt')) {
        $n = (Get-Content (Join-Path $Root 'UPDATE-MANIFEST.txt')).Count
        Say ("файлов в пакете: " + $n)
    }
    Say ("бэкап оставлен здесь: " + $Backup)
    exit 0
}

# --- 5. Откат ---
Say "ПАНЕЛЬ НЕ ПОДНЯЛАСЬ — откатываю"
Stop-Service $Service -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
if (Test-Path (Join-Path $Backup 'sender')) {
    Remove-Item (Join-Path $Root 'sender') -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $Backup 'sender') $Root -Recurse -Force
}
if (Test-Path (Join-Path $Backup 'web\dist')) {
    Remove-Item (Join-Path $Root 'web\dist') -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $Backup 'web\dist') (Join-Path $Root 'web') -Recurse -Force
}
Start-Service $Service
Start-Sleep -Seconds 5
if (Test-PanelAlive) { Say "откат удался, работает старая версия" }
else { Say "ВНИМАНИЕ: и после отката панель молчит — смотри логи службы" }
exit 1
