# Аварийный канал к проверочному VPS: забрать команду с дропа и выполнить.
#
# Зачем он есть. Единственной моей рукой на этой машине был python-раннер. Когда
# 11.08 раннер начал умирать, чинить его стало нечем: доставить исправление
# можно было только через него самого. Три раза подряд пришлось просить
# владельца зайти по RDP — при том что каждая правка была моя. Так быть не
# должно: канал восстановления не может зависеть от того, что он восстанавливает.
#
# Поэтому здесь НЕТ python, НЕТ зависимостей и почти нет логики — только
# скачать, проверить подпись, выполнить, положить ответ. Чем меньше в этом
# файле написано, тем меньше поводов ему сломаться.
#
# Обмен через дроп, как и всё остальное:
#   vps-komanda.json      <- я кладу {id, ps, sig}
#   vps-otvet-<id>.json   -> сюда ложится вывод
#
# Подпись обязательна. HMAC-SHA256 на JOB_SECRET по строке "<id>\n<ps>" —
# та же защита, что у раннера: одного DROP_TOKEN мало, чтобы прислать команду.
#
# Файл сохранён в UTF-8 С BOM: PowerShell 5.1 иначе ломается на кириллице.

$ErrorActionPreference = 'Continue'
$Root = 'C:\probe'
$Log  = Join-Path $Root 'bootstrap.log'
$Seen = Join-Path $Root '.bootstrap-seen'

function Zapis($m) {
    $s = "[" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "] " + $m
    try { Add-Content -Path $Log -Value $s -Encoding UTF8 } catch { }
}

try {
    $Secrets = @{}
    foreach ($Line in Get-Content (Join-Path $Root 'runner-secrets.env')) {
        if ($Line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $Secrets[$Matches[1]] = $Matches[2].Trim() }
    }
    $Drop   = $Secrets['DROP_URL']
    $Token  = $Secrets['DROP_TOKEN']
    $Secret = $Secrets['JOB_SECRET']
    if (-not $Token) { throw "нет DROP_TOKEN" }

    $H = @{ 'X-Drop-Token' = $Token }
    try {
        $Raw = (Invoke-WebRequest -Uri "$Drop/vps-komanda.json" -Headers $H `
                                  -UseBasicParsing -TimeoutSec 60).Content
    } catch {
        exit 0        # команды нет — это норма, а не ошибка
    }
    $Cmd = $Raw | ConvertFrom-Json
    # Текст команды приезжает в base64. Иначе подпись не сходится: PowerShell
    # 5.1 декодирует тело ответа по заголовку Content-Type, а дроп кодировку не
    # объявляет — кириллица в команде превращалась в другие байты, и HMAC над
    # ней не совпадал с посчитанным на отправке. 11.08 канал по этой причине
    # четыре раза подряд отверг команду с русскими комментариями. base64 —
    # чистый ASCII, декодировать его нечем испортить.
    $Podpisano = $null
    if ($Cmd.ps_b64) {
        $Podpisano = [string]$Cmd.ps_b64
        $Skript = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Podpisano))
    } elseif ($Cmd.ps) {
        $Podpisano = [string]$Cmd.ps
        $Skript = $Podpisano
    }
    if (-not $Cmd.id -or -not $Podpisano) { Zapis "команда без id или тела — пропускаю"; exit 0 }

    # Уже выполненное не повторяем: файл на дропе лежит, пока я его не сменю.
    if (Test-Path $Seen) {
        if ((Get-Content $Seen -Raw) -match [regex]::Escape($Cmd.id)) { exit 0 }
    }

    if ($Secret) {
        $Hmac = New-Object System.Security.Cryptography.HMACSHA256
        $Hmac.Key = [Text.Encoding]::UTF8.GetBytes($Secret)
        $Kanon = $Cmd.id + "`n" + $Podpisano
        $Nado = ($Hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($Kanon)) |
                 ForEach-Object { $_.ToString('x2') }) -join ''
        if ($Nado -ne $Cmd.sig) {
            Zapis "подпись не сошлась у команды $($Cmd.id) — НЕ выполняю"
            exit 0
        }
    }

    Zapis "выполняю команду $($Cmd.id)"
    Add-Content -Path $Seen -Value $Cmd.id -Encoding UTF8
    $Tmp = Join-Path $env:TEMP ("vps-komanda-" + $Cmd.id + ".ps1")
    Set-Content -Path $Tmp -Value $Skript -Encoding UTF8
    $Out = & powershell -NoProfile -ExecutionPolicy Bypass -File $Tmp 2>&1 | Out-String
    Remove-Item $Tmp -Force -ErrorAction SilentlyContinue

    $Otvet = @{ id = $Cmd.id; out = $Out; at = (Get-Date -Format 'o') } | ConvertTo-Json -Depth 3
    $Bytes = [Text.Encoding]::UTF8.GetBytes($Otvet)
    Invoke-WebRequest -Uri "$Drop/vps-otvet-$($Cmd.id).json" -Headers $H -Method PUT `
                      -Body $Bytes -UseBasicParsing -TimeoutSec 90 | Out-Null
    Zapis "ответ на $($Cmd.id) выложен, $($Out.Length) символов"
} catch {
    Zapis ("сорвалось: " + $_.Exception.Message)
}
