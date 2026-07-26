# Обновление ПАНЕЛИ ОБЗВОНА (служба obzvon, C:\seostat\app) из дропа.
# Запуск на сервере владельца:
#   powershell -ExecutionPolicy Bypass -File C:\sender\update-obzvon.ps1
#
# Почему отдельный скрипт, а не общий с рассыльщиком: обзвон живёт в C:\seostat\app,
# у него своя служба (obzvon), свой порт 8012 и своя Basic-авторизация (OBZVON_USERS),
# и операция panel_file_put туда не пишет — она ограничена C:\sender. Только дроп.
#
# Грабли, уже оплаченные на этой панели:
#  * 401 — это ШТАТНАЯ авторизация продажников, а не отказ. Первая выкатка пагинации
#    была откачена моим же скриптом, который принял 401 за падение.
#  * Маршруты смонтированы под /obzvon ДАЖЕ локально: проверять надо
#    http://127.0.0.1:8012/obzvon/kc, а не /kc — иначе штатный 404 примем за поломку.
#  * Файл в UTF-8 С BOM: PowerShell 5.1 иначе калечит кириллицу в парсере.

$ErrorActionPreference = 'Stop'
$App     = 'C:\seostat\app'
$Zip     = 'C:\sender\obzvon-update.zip'
$Stamp   = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup  = "C:\seostat\_bak-obzvon-" + $Stamp
$Service = 'obzvon'
$Health  = 'http://127.0.0.1:8012/obzvon/kc'
$DropUrl = 'https://parsercompressor.online/drop/obzvon-update.zip'

function Say($m) { Write-Host ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $m) }

function Test-ObzvonAlive {
    # Живой = не-5xx. 401 (Basic-авторизация) считаем УСПЕХОМ.
    try {
        $r = Invoke-WebRequest -Uri $Health -TimeoutSec 25 -UseBasicParsing
        return ($r.StatusCode -lt 500)
    } catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($resp -ne $null) { return ([int]$resp.StatusCode -lt 500) }
        return $false
    } catch { return $false }
}

# --- 1. Скачать пакет ---
$tok = (Select-String -Path 'C:\sender\server\runner-secrets.env' -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Say "качаю obzvon-update.zip с дропа"
Invoke-WebRequest -Uri $DropUrl -Headers @{'X-Drop-Token'=$tok} -OutFile $Zip
$size = (Get-Item $Zip).Length
if ($size -lt 500) { throw "архив подозрительно мал ($size байт) — выкатку отменяю" }
Say ("скачан: " + [math]::Round($size/1KB) + " КБ")

# --- 2. Бэкап: копируем только те файлы, которые архив перезапишет ---
Say "бэкап в $Backup"
New-Item -ItemType Directory -Path $Backup -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zf = [System.IO.Compression.ZipFile]::OpenRead($Zip)
try {
    foreach ($e in $zf.Entries) {
        if ([string]::IsNullOrEmpty($e.Name)) { continue }
        $rel = $e.FullName -replace '/', '\'
        $cur = Join-Path $App $rel
        if (Test-Path $cur) {
            $dst = Join-Path $Backup $rel
            New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
            Copy-Item $cur $dst -Force
        }
    }
} finally { $zf.Dispose() }

# --- 3. Стоп службы, распаковка, старт ---
Say "останавливаю $Service"
Stop-Service $Service -Force
Start-Sleep -Seconds 2
Say "распаковываю поверх $App"
Expand-Archive -Path $Zip -DestinationPath $App -Force
Say "запускаю $Service"
Start-Service $Service

# --- 4. Проверка живости ---
$ok = $false
foreach ($i in 1..10) {
    Start-Sleep -Seconds 3
    if (Test-ObzvonAlive) { $ok = $true; break }
    Say ("жду подъёма службы, попытка " + $i + "/10")
}

if ($ok) {
    Say "ГОТОВО: панель обзвона обновлена и отвечает"
    Say ("бэкап оставлен здесь: " + $Backup)
    exit 0
}

# --- 5. Откат ---
Say "ОБЗВОН НЕ ПОДНЯЛСЯ — откатываю"
Stop-Service $Service -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Get-ChildItem $Backup -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Backup.Length).TrimStart('\')
    Copy-Item $_.FullName (Join-Path $App $rel) -Force
}
Start-Service $Service
Start-Sleep -Seconds 5
if (Test-ObzvonAlive) { Say "откат удался, работает старая версия" }
else { Say "ВНИМАНИЕ: и после отката обзвон молчит — смотри логи службы obzvon" }
exit 1
