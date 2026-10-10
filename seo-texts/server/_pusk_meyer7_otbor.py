# -*- coding: utf-8 -*-
# Полный прогон Meyer, 10.10: повторный отбор вручную. Отбор финала шёл, когда шлюз не отдавал модели (Luna 503, затем
# 429 на источнике для кодинг-агентов): классификация 1 389 сайтов РБ и 17,7 тыс. сайтов без ИНН не прошла (решения не
# кэшируются — не потеряны). Повтор после того, как оркестратор ушёл дальше: кэши (DaData по названию, ОКВЭД, klass)
# берутся, классифицируется недостающее, список пишется под замком с журналами. Метка — как у шага оркестратора.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ЛОГ = os.path.join(DIR, 'konveyer_%s_pilot_otbor_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_otbor.py'), '--nabor=' + НАБОР, '--shag=pilot_otbor.py'], cwd=DIR,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все', KC_CEL='meyer',
                              POISK_NE_ZHDAT='1', POISK_CHECKO_MINUT='40', PILOT_SNIMKI='1', KC_BEZ_CHECKO='1',
                              PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna'))
выход.close()
time.sleep(30)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
