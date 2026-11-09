# -*- coding: utf-8 -*-
# Прогресс ca_fns_reestr.py и ca_pokupateli.py (только чтение)
import glob, json, os
P = r'C:\sender\server\ca'
o = {}
for имя in ('ca-zamer-progress.json', 'ca-pokupateli-progress.json'):
    try:
        o[имя] = json.load(open(os.path.join(P, имя), encoding='utf-8'))
    except Exception as e:  # noqa: BLE001
        o[имя] = repr(e)[:100]
for маска in ('ca_fns_reestr_*.log', 'ca_pokupateli_*.log'):
    лог = sorted(glob.glob(os.path.join(P, маска)))
    if лог:
        o[os.path.basename(лог[-1])] = open(лог[-1], encoding='utf-8', errors='replace').read()[-300:]
for f in glob.glob(r'C:\sender\_ops\ak\fns\data-*.zip*'):
    o[os.path.basename(f)] = round(os.path.getsize(f) / 2**20)
print('===ИТОГ===', json.dumps(o, ensure_ascii=False))
try:
    print('ТЕСТ', open(os.path.join(P, 'ca-testzip.json'), encoding='utf-8').read())
except Exception as e:  # noqa: BLE001
    print('ТЕСТ нет', repr(e)[:80])
