# -*- coding: utf-8 -*-
# Прогресс замера ca_fns_reestr.py (только чтение)
import glob, json, os
P = r'C:\sender\server\ca'
o = {'прогресс': json.load(open(os.path.join(P, 'ca-zamer-progress.json'), encoding='utf-8'))}
лог = sorted(glob.glob(os.path.join(P, 'ca_fns_reestr_*.log')))
if лог:
    o['хвост'] = open(лог[-1], encoding='utf-8', errors='replace').read()[-600:]
for f in glob.glob(r'C:\sender\_ops\ak\fns\data-*rsmp*') + glob.glob(r'C:\sender\_ops\ak\fns\data-*.zip*'):
    o[os.path.basename(f)] = round(os.path.getsize(f) / 2**20)
print('===ИТОГ===', json.dumps(o, ensure_ascii=False))
