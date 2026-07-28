# update-panel-meyer.ps1 — подхватить в панели новые ящики (Meyer, BOX15-17).
# Делает сам: находит свежие sender.yaml и sender-secrets.env в локальной папке
# дропа -> кладёт конфиг в C:\sender\sender.yaml (с бэкапом) -> вливает ВСЕ
# переменные из sender-secrets.env в окружение службы панели (существующие
# SENDER_CONFIG/UNSUB_SIGNING_SECRET и прочие НЕ затирает) -> перезапускает.
#
# Запуск: PowerShell ОТ АДМИНИСТРАТОРА:
#   powershell -ExecutionPolicy Bypass -File .\update-panel-meyer.ps1
# Переопределения при нестандартной раскладке:
#   -Service ИмяСлужбы  -SecretsFile C:\путь\sender-secrets.env  -YamlFile C:\путь\sender.yaml

param(
    [string]$Service = '',
    [string]$SecretsFile = '',
    [string]$YamlFile = ''
)

$ErrorActionPreference = 'Stop'
function Say([string]$m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn([string]$m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Die([string]$m)  { Write-Host "[x] $m" -ForegroundColor Red; exit 1 }
function Clean([string]$s) { if ($null -eq $s) { return '' } ($s -replace "`0", '').Trim() }

# --- 1) nssm и служба панели ------------------------------------------------
Say "1/5 Ищу nssm и службу панели"
$nssm = $null
foreach ($p in @("C:\nssm\win64\nssm.exe", "C:\nssm\nssm.exe")) { if (Test-Path $p) { $nssm = $p; break } }
if (-not $nssm) { $c = Get-Command nssm -ErrorAction SilentlyContinue; if ($c) { $nssm = $c.Source } }
if (-not $nssm) {
    $hit = Get-ChildItem C:\ -Recurse -Depth 3 -Filter nssm.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $nssm = $hit.FullName }
}
if (-not $nssm) { Die "nssm.exe не найден — укажи путь в скрипте" }

if (-not $Service) {
    foreach ($cand in @('RuspromSenderPanel')) {
        if (Get-Service $cand -ErrorAction SilentlyContinue) { $Service = $cand; break }
    }
}
if (-not $Service) {
    $svc = Get-CimInstance Win32_Service | Where-Object {
        $_.Name -match 'sender|panel|rusprom' -or $_.DisplayName -match 'sender|panel|rusprom'
    } | Select-Object -First 1
    if ($svc) { $Service = $svc.Name }
}
if (-not $Service) { Die "Служба панели не найдена. Запусти с -Service ИмяСлужбы (смотри 'nssm list' или services.msc)" }
Say "nssm: $nssm | служба: $Service"

# --- 2) свежие файлы из локальной папки дропа --------------------------------
Say "2/5 Ищу свежие sender.yaml и sender-secrets.env (папка дропа)"
function FindNewest([string]$name, [string]$explicit) {
    if ($explicit) { if (Test-Path $explicit) { return (Get-Item $explicit) } else { Die "Нет файла: $explicit" } }
    $roots = @()
    $roots += Get-ChildItem C:\ -Recurse -Depth 3 -Directory -Filter 'drop-storage' -ErrorAction SilentlyContinue
    $files = @()
    foreach ($r in $roots) {
        $files += Get-ChildItem $r.FullName -Filter $name -ErrorAction SilentlyContinue
    }
    if (-not $files) {
        $files = Get-ChildItem C:\seostat -Recurse -Depth 3 -Filter $name -ErrorAction SilentlyContinue
    }
    $files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
$secrets = FindNewest 'sender-secrets.env' $SecretsFile
$yaml    = FindNewest 'sender.yaml' $YamlFile
if (-not $secrets) { Die "sender-secrets.env не найден (скачай с дропа или укажи -SecretsFile)" }
if (-not $yaml)    { Die "sender.yaml не найден (скачай с дропа или укажи -YamlFile)" }
Say "секреты: $($secrets.FullName) ($(Get-Date $secrets.LastWriteTime -Format 'dd.MM HH:mm'))"
Say "конфиг:  $($yaml.FullName) ($(Get-Date $yaml.LastWriteTime -Format 'dd.MM HH:mm'))"
$boxCount = (Select-String -Path $yaml.FullName -Pattern 'mailbox_id' -AllMatches).Count
Say "в конфиге ящиков: $boxCount (ожидаем 17: 14 КЦ + 3 Meyer)"

# --- 3) конфиг на место (с бэкапом) -----------------------------------------
Say "3/5 Кладу конфиг"
# куда: из текущего SENDER_CONFIG службы, иначе дефолт C:\sender\sender.yaml
$rawEnv = & $nssm get $Service AppEnvironmentExtra 2>$null
$curEnv = @{}
foreach ($line in @($rawEnv)) {
    $l = Clean "$line"
    if ($l -and $l.Contains('=')) {
        $k, $v = $l.Split('=', 2)
        $curEnv[$k] = $v
    }
}
$dest = 'C:\sender\sender.yaml'
if ($curEnv.ContainsKey('SENDER_CONFIG') -and $curEnv['SENDER_CONFIG']) { $dest = $curEnv['SENDER_CONFIG'] }
if ((Test-Path $dest) -and ((Get-Item $dest).FullName -ne $yaml.FullName)) {
    $bak = "$dest.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $dest $bak
    Say "Бэкап старого конфига: $bak"
}
if ((Get-Item $dest -ErrorAction SilentlyContinue).FullName -ne $yaml.FullName) {
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item $yaml.FullName $dest -Force
}
Say "Конфиг панели: $dest"

# --- 4) слить переменные из sender-secrets.env в окружение службы -----------
Say "4/5 Вливаю переменные (BOX* и прочие) в окружение службы"
$added = 0
foreach ($line in Get-Content $secrets.FullName) {
    $l = $line.Trim()
    if (-not $l -or $l.StartsWith('#')) { continue }
    if ($l.Contains('=')) {
        $k, $v = $l.Split('=', 2)
        if ($v) {
            if (-not $curEnv.ContainsKey($k) -or $curEnv[$k] -ne $v) { $added++ }
            $curEnv[$k] = $v
        }
    }
}
if (-not $curEnv.ContainsKey('SENDER_CONFIG')) { $curEnv['SENDER_CONFIG'] = $dest }
$pairs = @()
foreach ($k in ($curEnv.Keys | Sort-Object)) { $pairs += "$k=$($curEnv[$k])" }
& $nssm set $Service AppEnvironmentExtra @pairs | Out-Null
Say "Переменных в окружении службы: $($pairs.Count) (обновлено/добавлено: $added)"

# --- 5) перезапуск и проверка ------------------------------------------------
Say "5/5 Перезапускаю панель"
& $nssm restart $Service | Out-Null
Start-Sleep -Seconds 4
$status = Clean ((& $nssm status $Service) -join ' ')
Say "Статус службы: $status"
if ($status -notmatch 'RUNNING') { Die "Служба не поднялась — смотри C:\sender\logs\panel.err.log и пришли хвост Клоду" }

# порт из аргументов службы
$appArgs = Clean ((& $nssm get $Service AppParameters 2>$null) -join ' ')
$port = '8090'
if ($appArgs -match '--port\s+(\d+)') { $port = $Matches[1] }
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 10
    Say "Панель отвечает на 127.0.0.1:$port (HTTP $($r.StatusCode))"
} catch {
    Warn "Панель не ответила на 127.0.0.1:$port — проверь порт/логи ($($_.Exception.Message))"
}

Write-Host ""
Say "ГОТОВО. В панели: Ящики/Готовность — должны появиться 3 ящика Meyer:"
Write-Host "  a.miroshnichenko@optic-sort.ru | a.kozlov@zernosort.ru | i.kuznetsova@sort-systems.ru"
Write-Host "  (v.ivanov@sort-inspection.ru добавим после решения тарифа VK)"
