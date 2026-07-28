# setup-redirects.ps1 — редиректор доменов-двойников для Windows-сервера с Caddy.
# (parsercompressor.online: Caddy терминирует 443 и проксирует drop — редиректы
# дописываются отдельными site-блоками, дроп не трогаем; сертификаты на новые
# домены Caddy выпустит САМ, как только их A-записи доедут до этого сервера.)
#
# Запуск: PowerShell ОТ АДМИНИСТРАТОРА, из папки со скриптом:
#   powershell -ExecutionPolicy Bypass -File .\setup-redirects.ps1
# Если Caddyfile лежит в нестандартном месте:
#   powershell -ExecutionPolicy Bypass -File .\setup-redirects.ps1 -Caddyfile "C:\caddy\Caddyfile"
#
# Идемпотентен: повторный запуск обновляет блок между маркерами, не плодит копии.

param([string]$Caddyfile = '')

$ErrorActionPreference = 'Stop'
$MarkerBegin = '# ===== RUSPROM-REDIRECTS BEGIN ====='
$MarkerEnd   = '# ===== RUSPROM-REDIRECTS END ====='

# 7 доменов КЦ -> prokompressor.ru; 4 домена Meyer -> vsefotoseparatory.ru
# (3 домена RU-CENTER на холде, сюда не входят.)
$RedirectConf = @"
$MarkerBegin
# 301-редиректы доменов-двойников (источник: sender/config/domains.json)
kompressor-air-trade.ru, www.kompressor-air-trade.ru, kompressor-pro-expert.ru, www.kompressor-pro-expert.ru, kompressor-air-expert.ru, www.kompressor-air-expert.ru, compressor-air-expert.ru, www.compressor-air-expert.ru, kompressor-expert.ru, www.kompressor-expert.ru, kompressor-pro-trade.ru, www.kompressor-pro-trade.ru, compressor-store.ru, www.compressor-store.ru {
	redir https://prokompressor.ru{uri} permanent
}

sort-inspection.ru, www.sort-inspection.ru, optic-sort.ru, www.optic-sort.ru, zernosort.ru, www.zernosort.ru, sort-systems.ru, www.sort-systems.ru {
	redir https://vsefotoseparatory.ru{uri} permanent
}
$MarkerEnd
"@

function Say([string]$msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn([string]$msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Die([string]$msg)  { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

# --- 1) найти caddy.exe и службу -------------------------------------------
Say "1/5 Ищу caddy.exe и его службу"
$caddyExe = $null
$caddySvc = $null

$cmd = Get-Command caddy -ErrorAction SilentlyContinue
if ($cmd) { $caddyExe = $cmd.Source }

$svc = Get-CimInstance Win32_Service | Where-Object {
    $_.PathName -match 'caddy' -or $_.Name -match 'caddy'
} | Select-Object -First 1
if ($svc) {
    $caddySvc = $svc.Name
    if (-not $caddyExe -and $svc.PathName -match '"?([A-Za-z]:\\[^"]*caddy[^"]*\.exe)"?') {
        $caddyExe = $Matches[1]
    }
    # служба через NSSM: PathName укажет на nssm.exe — достанем реальный exe
    if (-not $caddyExe -and $svc.PathName -match 'nssm') {
        $nssm = ($svc.PathName -split '\s+')[0].Trim('"')
        try { $caddyExe = (& $nssm get $svc.Name Application 2>$null | Select-Object -First 1).Trim() } catch {}
    }
}
if (-not $caddyExe) {
    foreach ($p in @("C:\caddy\caddy.exe", "C:\Program Files\caddy\caddy.exe",
                     "C:\ProgramData\chocolatey\bin\caddy.exe", "C:\seostat\caddy.exe",
                     "C:\tools\caddy\caddy.exe")) {
        if (Test-Path $p) { $caddyExe = $p; break }
    }
}
if (-not $caddyExe) { Die "caddy.exe не найден. Запусти с указанием пути: -Caddyfile и поправь `$caddyExe в скрипте, либо скажи Клоду, где стоит Caddy." }
$svcNote = ''
if ($caddySvc) { $svcNote = " (служба: $caddySvc)" }
Say "caddy.exe: $caddyExe$svcNote"

# --- 2) найти Caddyfile -----------------------------------------------------
Say "2/5 Ищу Caddyfile"
if (-not $Caddyfile) {
    $candidates = @()
    if ($svc -and $svc.PathName -match '--config\s+"?([^"\s]+)"?') { $candidates += $Matches[1] }
    if ($svc -and $svc.PathName -match 'nssm') {
        $nssm = ($svc.PathName -split '\s+')[0].Trim('"')
        try {
            $appArgs = (& $nssm get $svc.Name AppParameters 2>$null) -join ' '
            if ($appArgs -match '--config\s+"?([^"\s]+)"?') { $candidates += $Matches[1] }
        } catch {}
    }
    $candidates += @(
        (Join-Path (Split-Path $caddyExe) 'Caddyfile'),
        'C:\caddy\Caddyfile', 'C:\seostat\Caddyfile',
        'C:\Program Files\caddy\Caddyfile', 'C:\ProgramData\caddy\Caddyfile'
    )
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { $Caddyfile = $c; break } }
}
if (-not $Caddyfile -or -not (Test-Path $Caddyfile)) {
    Die "Caddyfile не найден автоматически. Найди его (обычно рядом с caddy.exe) и перезапусти: -Caddyfile `"C:\путь\Caddyfile`""
}
Say "Caddyfile: $Caddyfile"

# --- 3) бэкап и вставка блока редиректов -----------------------------------
Say "3/5 Дописываю блок редиректов (с бэкапом)"
$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "$Caddyfile.bak-$stamp"
Copy-Item $Caddyfile $backup
Say "Бэкап: $backup"

$content = [IO.File]::ReadAllText($Caddyfile)
$pattern = [regex]::Escape($MarkerBegin) + '[\s\S]*?' + [regex]::Escape($MarkerEnd)
if ($content -match $pattern) {
    $content = [regex]::Replace($content, $pattern, $RedirectConf.Replace('$', '$$'))
    Say "Нашёл старый блок между маркерами — обновил его"
} else {
    if (-not $content.EndsWith("`n")) { $content += "`r`n" }
    $content += "`r`n" + $RedirectConf + "`r`n"
    Say "Дописал новый блок в конец Caddyfile"
}
[IO.File]::WriteAllText($Caddyfile, $content, (New-Object System.Text.UTF8Encoding($false)))

# --- 4) проверка конфига и перезагрузка Caddy ------------------------------
Say "4/5 Проверяю конфиг и перезагружаю Caddy"
& $caddyExe validate --config $Caddyfile
if ($LASTEXITCODE -ne 0) {
    Copy-Item $backup $Caddyfile -Force
    Die "caddy validate не прошёл — вернул Caddyfile из бэкапа, ничего не изменилось. Пришли вывод ошибки Клоду."
}
& $caddyExe reload --config $Caddyfile
if ($LASTEXITCODE -ne 0) {
    Warn "caddy reload не сработал (admin API выключен?) — пробую перезапустить службу"
    if ($caddySvc) { Restart-Service $caddySvc -Force; Say "Служба $caddySvc перезапущена" }
    else { Die "Перезапусти Caddy вручную (служба/процесс) — конфиг уже на месте." }
}

# --- 5) фаервол + итог ------------------------------------------------------
Say "5/5 Проверяю фаервол (80/443)"
foreach ($rule in @(@('RUSPROM-HTTP', 80), @('RUSPROM-HTTPS', 443))) {
    if (-not (Get-NetFirewallRule -DisplayName $rule[0] -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule[0] -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $rule[1] | Out-Null
        Say "Открыл порт $($rule[1]) ($($rule[0]))"
    }
}

Write-Host ""
Say "ГОТОВО. Что дальше:"
Write-Host @"
 - Сертификаты Caddy выпускает сам, в фоне, по мере того как A-записи доменов
   доезжают до этого сервера. Недоехавшие домены он молча ретраит - ничего
   перезапускать не надо.
 - Проверка (можно через пару минут после доезда DNS):
     curl.exe -I https://kompressor-air-trade.ru/   -> 301 Location: https://prokompressor.ru/
     curl.exe -I https://zernosort.ru/              -> 301 Location: https://vsefotoseparatory.ru/
 - Логи выпуска сертов: журнал Caddy (если через NSSM - его лог-файл).
 - Откат: копия старого конфига лежит рядом ($backup).
"@
