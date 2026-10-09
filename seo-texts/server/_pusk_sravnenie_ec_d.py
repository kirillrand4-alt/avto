# -*- coding: utf-8 -*-
# Сравнение, фаза D: повтор C новой версией обхода (разбор номеров 3+3 и через дробь) — отдельным процессом.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
ЛОГ = os.path.join(DIR, 'konveyer_%s_sravnenie_ec_D_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_sravnenie_ec.py'), '--nabor=' + НАБОР, '--shag=sravnenie_ec_D'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', KC_BEZ_CHECKO='1',
                              KC_ZAKUPKI_OT='1e12', PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-6-luna',
                              KC_SRAV_N=os.environ.get('KC_SRAV_N', '30'), KC_SRAV_POTOKOV='8', KC_SRAV_FAZY='D'))
выход.close()
time.sleep(30)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
