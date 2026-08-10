# -*- coding: utf-8 -*-
"""Кладёт routes_park.py в приложение и перезапускает службу обзвона.

С копией перед заменой и с проверкой, что служба поднялась: панель, которая молча легла
после деплоя, хуже панели без новой страницы.
"""
import json, os, shutil, subprocess, time, urllib.request

IST = r'C:\sender\_ops\routes_park.py'
CEL = r'C:\seostat\app\api\routes_park.py'
o = {}
if not os.path.exists(IST):
    print(json.dumps({'ОШИБКА': 'нет исходника ' + IST}, ensure_ascii=False)); raise SystemExit
if os.path.exists(CEL):
    bak = CEL + '.bak-%d' % int(time.time())
    shutil.copyfile(CEL, bak)
    o['kopiya'] = os.path.basename(bak)
shutil.copyfile(IST, CEL)
o['polozheno'] = os.path.getsize(CEL)

r = subprocess.run(['powershell', '-Command', 'Restart-Service obzvon -Force; Start-Sleep 6; '
                                              '(Get-Service obzvon).Status'],
                   capture_output=True, text=True, timeout=180)
o['sluzhba'] = (r.stdout or r.stderr).strip()[-60:]
for popytka in range(6):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8012/obzvon/centro/login', timeout=15) as f:
            o['vhod_http'] = f.status
        break
    except Exception as e:
        o['vhod_http'] = str(e)[:80]
        time.sleep(4)
print(json.dumps(o, ensure_ascii=False, indent=1))
