# -*- coding: utf-8 -*-
"""Почему Зенка стоит: установлена ли, есть ли служба, когда перезагружался сервер."""
import json, os, subprocess, glob

o = {}
def ps(cmd, tmo=120):
    r = subprocess.run(['powershell','-NoProfile','-Command',cmd],
                       capture_output=True, text=True, timeout=tmo)
    return (r.stdout or r.stderr or '').strip()[:700]

o['аптайм_и_загрузка'] = ps("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime")
o['служба_zenno'] = ps("Get-Service *zenno* -ErrorAction SilentlyContinue | "
                       "Select-Object Name,Status,StartType | ConvertTo-Json -Compress") or 'служб нет'
o['exe'] = ps("Get-ChildItem 'C:\\Program Files*\\ZennoLab' -Recurse -Filter 'ZennoPoster*.exe' "
              "-ErrorAction SilentlyContinue | Select-Object -First 3 FullName | ConvertTo-Json -Compress") or 'не найдено'
o['автозапуск'] = ps("Get-CimInstance Win32_StartupCommand | Where-Object {$_.Command -like '*enno*'} | "
                     "Select-Object Name,Command | ConvertTo-Json -Compress") or 'нет'
o['сессии'] = ps("quser 2>&1 | Out-String")
# когда в последний раз мост что-то писал
лог = glob.glob(r'C:\sender\server\zenno*.log') + glob.glob(r'C:\seostat\drop\zenno\*.log')
import time
o['логи_моста'] = [{'файл': os.path.basename(p),
                    'изменён': time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(p)))}
                   for p in sorted(лог, key=os.path.getmtime)[-4:]]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:3000])
