# -*- coding: utf-8 -*-
# 11.10: полный шаг «группы компаний» (kc_gruppy) для meyer7 — после свежих kc_dorazmetka/kc_audit/kc_sayt_proverka
# (группа = общий хост с ≥2 доказанными членами). Фоном, резюм по домену (<набор>-gruppy.jsonl, fsync), копия на дроп.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
лог = os.path.join(DIR, 'konveyer_meyer7_gruppy_%s.log' % time.strftime('%d%m-%H%M'))
with open(лог, 'wb') as в:
    p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_gruppy.py'), '--metka=gruppy_meyer7'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False,
                         env=dict(os.environ, KC_NABOR='meyer7', KC_CEL='meyer', PYTHONIOENCODING='utf-8',
                                  PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna'))
time.sleep(60)
print('===ИТОГ===')
print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                 ensure_ascii=False, indent=1))
