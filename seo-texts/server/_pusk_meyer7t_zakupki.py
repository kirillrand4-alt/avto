# -*- coding: utf-8 -*-
# Проба meyer7t: контакты закупок ЕИС от выручки 120 млн (kc_zakupki_dobor.py) — замер скорости и отдачи.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'konveyer_meyer7t_kc_zakupki_dobor_%s.log' % time.strftime('%d%m-%H%M'))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_zakupki_dobor.py'), '--nabor=meyer7t', '--shag=kc_zakupki_dobor.py'],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT,
                     close_fds=False, env=dict(os.environ, KC_NABOR='meyer7t', POISK_NABOR='meyer7t', KC_CEL='meyer',
                                               KC_ZAKUPKI_DOBOR_OT='120e6', KC_ZAKUPKI_POTOKOV='6'))
выход.close()
time.sleep(30)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=1))
