<#
.SYNOPSIS
    Сбор спроса Wordstat по ОБЕИМ базам ключей, все гранулярности за прогон.

.DESCRIPTION
    Гоняет C:\seostat\scripts\wordstat.py по одному прогону на базу с --graph all
    (month+week+day сразу). Два прогона, а не шесть: у сборщика есть --graph all,
    он наполняет и wordstat_history (месяц), и wordstat_series (неделя/день).

    По умолчанию БЕЗ --skip-done. Справка сборщика: --skip-done пропускает фразы,
    уже собранные «за этот регион/устройство/период», и назначен «для возобновления
    большого прогона». Для подтягивания свежих периодов он мешает, поэтому включается
    отдельно ключом -Resume — им же добивают прогон, который прервался.

.EXAMPLE
    .\wordstat-sbor-vse.ps1 -ShowLists
    Что загружено в базах ключей. Прогнать первым.

.EXAMPLE
    .\wordstat-sbor-vse.ps1 -DryRun
    Показать команды, ничего не запуская.

.EXAMPLE
    .\wordstat-sbor-vse.ps1
    Полный сбор: обе базы, month+week+day.

.EXAMPLE
    .\wordstat-sbor-vse.ps1 -Resume
    Добить прогон, который оборвался (добавляет --skip-done).
#>
[CmdletBinding()]
param(
    # Боевой проект. На машине есть вторая копия C:\seostat-centro-review со своей БД —
    # сбор туда на боевую вкладку «Спрос» не попадёт.
    [string]$Root = 'C:\seostat',

    # Базы ключей вкладки «Спрос» (--base). Порядок = порядок сбора.
    [string[]]$Bases = @('прокомпрессор', 'meyer'),

    # all = month+week+day за один прогон.
    [ValidateSet('month', 'week', 'day', 'all')]
    [string]$Graph = 'all',

    # broad — как есть. all = все 4 типа, но это вчетверо больше запросов и капчи.
    [ValidateSet('broad', 'phrase', 'exact', 'order', 'all')]
    [string]$Match = 'broad',

    # auto — облачный решатель (нужен сохранённый ключ: --set-captcha).
    # manual — решать руками в открытом браузере (ты за машиной — рабочий вариант).
    [ValidateSet('manual', 'auto', 'auto-only')]
    [string]$Captcha = 'auto',

    # list — как в списке; freq — сначала самые частотные (полезно, если прогон могут
    # прервать: ценное соберётся первым). freq опирается на уже собранные месячные данные.
    [ValidateSet('list', 'freq')]
    [string]$Order = 'list',

    # Пауза между запросами к Wordstat, сек. По умолчанию 0: владелец 07.10 — «там нет
    # никаких капч вообще, убрать паузу». Дефолт сборщика 2.0 с был осторожностью без
    # замера и съедал почти всё время прогона (~9 ч на базу «прокомпрессор»).
    # Если в строках прогона пойдёт расти fail= — это первый признак, что Яндекс начал
    # притормаживать: тогда вернуть паузу, например -Delay 1.
    # Строкой, а не числом: на рус. локали [double]0.2 сериализуется как «0,2»,
    # и python argparse на «0,2» падает. Строку отдаём в argv как есть.
    [string]$Delay = '0',

    # Добавить --skip-done: ТОЛЬКО для возобновления оборвавшегося прогона.
    [switch]$Resume,

    # Показать базы ключей и выйти.
    [switch]$ShowLists,

    # Показать команды и выйти.
    [switch]$DryRun,

    [string]$LogDir = ''
)

$ErrorActionPreference = 'Stop'

# --- кодировки: кириллица ломается сразу в трёх местах ---
# 1. argv: имя базы «прокомпрессор» уходит в python аргументом;
# 2. вывод python с русским текстом -> UnicodeEncodeError в конце длинного прогона;
# 3. лог-файл.
try { chcp 65001 > $null } catch { }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# --- проверки ДО запуска: тихий «успех» на кривом пути дороже раннего падения ---
if (-not (Test-Path -LiteralPath $Root)) { throw "Нет каталога проекта: $Root" }
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $py))                          { throw "Нет питона venv: $py" }
if (-not (Test-Path -LiteralPath (Join-Path $Root 'scripts\wordstat.py'))) { throw "Нет сборщика: $Root\scripts\wordstat.py" }

# Пауза: «0,2» (рус. ввод) -> «0.2», иначе python argparse не разберёт. Валидируем,
# чтобы кривой ввод упал сразу, а не ушёл мусором в --delay.
if ($Delay) {
    $Delay = $Delay -replace ',', '.'
    if ($Delay -notmatch '^\d+(\.\d+)?$') { throw "Плохое -Delay: '$Delay' (нужно число, напр. 0.2)" }
}

if (-not $LogDir) { $LogDir = Join-Path $Root 'logs' }
if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$log = Join-Path $LogDir "wordstat-vse-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

Push-Location -LiteralPath $Root
try {
    if ($ShowLists) {
        & $py 'scripts\wordstat.py' '--show-lists' 2>&1 | Tee-Object -FilePath $log -Append
        return
    }

    Write-Host "Проект     : $Root"
    Write-Host "Лог        : $log"
    Write-Host "Базы       : $($Bases -join ', ')"
    Write-Host "Гранул.    : $Graph$(if ($Graph -eq 'all') { '  (month+week+day за прогон)' })"
    Write-Host "Частотность: $Match    Капча: $Captcha    Порядок: $Order    Пауза: $(if ($Delay) { "$Delay c" } else { 'дефолт (~2.0 c)' })"
    Write-Host "Режим      : $(if ($Resume) { 'ВОЗОБНОВЛЕНИЕ (--skip-done)' } else { 'полный сбор' })"
    Write-Host ('-' * 76)

    $itogi = @()
    foreach ($b in $Bases) {
        $argumenty = @('scripts\wordstat.py', '--collect', '--from-list', '--base', $b,
                       '--graph', $Graph, '--dedup',       # dedup экономит запросы и капчу
                       '--captcha', $Captcha, '--order', $Order)
        if ($Match -ne 'broad') { $argumenty += @('--match', $Match) }
        if ($Delay)             { $argumenty += @('--delay', $Delay) }
        if ($Resume)            { $argumenty += '--skip-done' }

        if ($DryRun) { Write-Host "[dry] $py $($argumenty -join ' ')"; continue }

        Write-Host ""
        Write-Host ">>> [$b] старт $(Get-Date -Format 'HH:mm:ss')"
        Write-Host "    $($argumenty -join ' ')"
        "`n===== [$b] старт $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" |
            Add-Content -LiteralPath $log -Encoding UTF8

        $t0 = Get-Date
        # 2>&1 — stderr тоже в лог: диагностика капчи и логина уходит именно туда.
        & $py @argumenty 2>&1 | Tee-Object -FilePath $log -Append
        # PowerShell не бросает исключение на ненулевой код внешней программы:
        # без явной проверки сбой прошёл бы как успех.
        $rc = $LASTEXITCODE
        $sek = [int]((Get-Date) - $t0).TotalSeconds

        $itogi += [pscustomobject]@{
            Baza = $b; Kod = $rc; Minut = [math]::Round($sek / 60, 1)
            Itog = $(if ($rc -eq 0) { 'ок' } else { 'СБОЙ' })
        }
        Write-Host "<<< [$b] код=$rc, $([math]::Round($sek/60,1)) мин"

        # Намеренно НЕ прерываемся на сбое первой базы: вторую собрать всё равно надо.
    }

    if ($DryRun) { Write-Host "`n(dry-run: ничего не запускалось)"; return }

    Write-Host ""
    Write-Host ('=' * 76)
    $svodka = $itogi | Format-Table -AutoSize | Out-String
    Write-Host $svodka
    $svodka | Add-Content -LiteralPath $log -Encoding UTF8

    Write-Host "Что собрано сейчас (--status):"
    & $py 'scripts\wordstat.py' '--status' 2>&1 | Tee-Object -FilePath $log -Append

    $upalo = @($itogi | Where-Object { $_.Kod -ne 0 })
    if ($upalo.Count -gt 0) {
        Write-Warning "Сбоев: $($upalo.Count) из $($itogi.Count). Лог: $log"
        Write-Warning "Добить оборвавшееся:  .\wordstat-sbor-vse.ps1 -Resume"
        exit 1
    }
    Write-Host "Готово: обе базы собраны. На вкладке «Спрос» нажми «обновить» (кэш страницы — час)."
}
finally {
    Pop-Location
}
