# -*- coding: utf-8 -*-
r"""fixKP (22.10): куда ушла память сверх процессов – счётчики Windows (пулы ядра, кэш, изменённые страницы, вирт. машины).
Только чтение.

    python3 zapusk_na_servere.py fixKP_pamyat2.py
"""
import json
import subprocess

PS = ("Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object AvailableMBytes,CacheBytes,CommittedBytes,"
      "CommitLimit,ModifiedPageListBytes,PoolNonpagedBytes,PoolPagedBytes,StandbyCacheCoreBytes,StandbyCacheNormalPriorityBytes,"
      "StandbyCacheReserveBytes,FreeAndZeroPageListBytes,SystemDriverResidentBytes,SystemCodeResidentBytes | ConvertTo-Json")
r = subprocess.run(['powershell', '-NoProfile', '-Command', PS], capture_output=True, timeout=120)
d = json.loads(r.stdout.decode('utf-8', 'replace'))
for k, v in d.items():
    print('  %-34s %8.2f ГБ' % (k, (v * 2**20 if k == 'AvailableMBytes' else v) / 2**30))
for cmd, imya in (("Get-Process vmmem*,vmwp*,VBox*,MemCompression -ErrorAction SilentlyContinue | Select-Object Name,Id,WorkingSet64 | ConvertTo-Json", 'вирт. машины / сжатие памяти'),
                  ("Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage | ConvertTo-Json", 'файл подкачки')):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, timeout=60)
    print('%s: %s' % (imya, r.stdout.decode('utf-8', 'replace').strip()[:400] or 'нет'))
