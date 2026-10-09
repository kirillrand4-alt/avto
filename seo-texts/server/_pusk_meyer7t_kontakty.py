# -*- coding: utf-8 -*-
# Проба meyer7t: обход отдельным процессом с KC_POTOKOV (09.10: в 24 потока шёл ~29 компаний/мин против ~150 в пилоте —
# потоки ждут медленные сайты; резюм: обойдённые пропускаются). Окружение — как у шага обхода в pilot_konveyer.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7t'
ЛОГ = os.path.join(DIR, 'konveyer_%s_kc_kontakty_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_kontakty.py'), '--nabor=' + НАБОР, '--shag=kc_kontakty.py'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1',
                              KC_BEZ_CHECKO='1', KC_ZAKUPKI_OT='1e9', KC_POTOKOV=os.environ.get('KC_POTOKOV_PROBA', '24'),
                              PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-6-luna'))
выход.close()
time.sleep(40)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
