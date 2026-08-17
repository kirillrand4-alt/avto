# -*- coding: utf-8 -*-
r"""Кто занимает оперативку на сервере — с командной строкой, а не just «python».

Владелец 17.08 выключил Зенку, а память осталась занята наполовину. Вопрос
законный: у нас на сервере живёт десяток своих процессов (панель, обогащение,
цикл фактов, поиск сайтов, мост Зенки, браузеры), и «python.exe 400 МБ» в
диспетчере задач ничего не объясняет. Здесь каждый процесс подписан своей
командной строкой и сгруппирован по нашему смыслу.

    python pamyat.py [сколько_строк]
"""
import json
import re
import subprocess
import sys

PS = r'''
$os = Get-CimInstance Win32_OperatingSystem
$all = Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine,WorkingSetSize
$out = [ordered]@{
  vsego_mb  = [int]($os.TotalVisibleMemorySize/1KB)
  svobodno_mb = [int]($os.FreePhysicalMemory/1KB)
  processy = @($all | Sort-Object WorkingSetSize -Descending | Select-Object -First 30 |
    ForEach-Object { [ordered]@{
        pid = $_.ProcessId
        imya = $_.Name
        mb = [int]($_.WorkingSetSize/1MB)
        cmd = if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(160, $_.CommandLine.Length)) } else { '' }
    } })
  summa_processov_mb = [int](($all | Measure-Object WorkingSetSize -Sum).Sum/1MB)
  kesh_fajlov_mb = [int]((Get-CimInstance Win32_PerfRawData_PerfOS_Memory).StandbyCacheNormalPriorityBytes/1MB)
  kesh_vsego_mb = [int]((Get-CimInstance Win32_PerfRawData_PerfOS_Memory).CacheBytes/1MB)
  processov_shtuk = $all.Count
  po_imenam = @($all | Group-Object Name | ForEach-Object { [ordered]@{
        imya = $_.Name
        shtuk = $_.Count
        mb = [int](($_.Group | Measure-Object WorkingSetSize -Sum).Sum/1MB)
    } } | Sort-Object { $_.mb } -Descending | Select-Object -First 15)
}
$out | ConvertTo-Json -Depth 4 -Compress
'''
# наши процессы узнаём по куску командной строки — так видно, что именно жрёт
НАШИ = (('цикл фактов', 'fakty_cikl'), ('поиск сайтов', 'poisk_saytov'),
        ('мост Зенки', 'zenno_most'), ('обогащение', 'enrich_contacts'),
        ('панель рассыльщика', 'sender'), ('панель обогащения', 'enrich_panel'),
        ('дроп', 'drop_server'), ('раннер', 'job_runner'), ('обзвон', 'app.obzvon'),
        ('сеостат', 'app.main'), ('парсер', 'webui.py'), ('парсер2', 'serve.py'),
        ('браузер', 'chrome'), ('зенка', 'ZennoPoster'))


def свои(процессы):
    итог = {}
    for p in процессы:
        подпись = 'прочее: ' + p['imya']
        низ = (p.get('cmd') or '').lower()
        for имя, кусок in НАШИ:
            if кусок.lower() in низ or кусок.lower() in p['imya'].lower():
                подпись = имя
                break
        б = итог.setdefault(подпись, {'штук': 0, 'мб': 0})
        б['штук'] += 1
        б['мб'] += p['mb']
    return dict(sorted(итог.items(), key=lambda kv: -kv[1]['мб']))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 14
    p = subprocess.run(['powershell', '-NoProfile', '-Command', PS],
                       capture_output=True, text=True, timeout=240)
    т = p.stdout.strip()
    i = т.find('{')
    d = json.loads(т[i:]) if i >= 0 else {}
    процессы = d.get('processy') or []
    занято = (d.get('vsego_mb', 0) - d.get('svobodno_mb', 0))
    print(json.dumps({'верх_по_памяти': [
        {'мб': x['mb'], 'кто': re.sub(r'\s+', ' ', (x.get('cmd') or x['imya']))[:110],
         'pid': x['pid']} for x in процессы[:n]]}, ensure_ascii=False, indent=1))
    print(json.dumps({'всего_мб': d.get('vsego_mb'), 'свободно_мб': d.get('svobodno_mb'),
                      'занято_мб': занято,
                      'сумма_всех_процессов_мб': d.get('summa_processov_mb'),
                      'процессов_штук': d.get('processov_shtuk'),
                      'файловый_кэш_windows_мб': d.get('kesh_fajlov_mb'),
                      'кэш_всего_мб': d.get('kesh_vsego_mb'),
                      'занято_процентов': (round(100 * занято / d['vsego_mb'])
                                           if d.get('vsego_mb') else None),
                      'наши_потребители': свои(процессы)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
