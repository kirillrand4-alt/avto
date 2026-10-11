# -*- coding: utf-8 -*-
# 11.10: доизвлечение номеров из кэша (kc_doizvlech, ревизия №42), затем добор закупок ЕИС от 120 млн (kc_zakupki_dobor,
# пауза 1,5 с на запрос) — ПОСЛЕДОВАТЕЛЬНО одним отдельным процессом: оба дописывают копии последней записи компании в
# meyer7-kontakty.jsonl, параллельно — гонка. Оба останавливаются, если оркестратор начал шаги после агентов.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ЛОГ = os.path.join(DIR, 'konveyer_%s_doizv_zakupki_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
код = ('import subprocess, sys\n'
       'r = subprocess.run([sys.executable, "-u", r"%s\\kc_doizvlech.py"])\n'
       'print("доизвлечение: код", r.returncode, flush=True)\n'
       'r = subprocess.run([sys.executable, "-u", r"%s\\kc_zakupki_dobor.py"])\n'
       'print("закупки: код", r.returncode, flush=True)\n') % (DIR, DIR)
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', '-c', код, '--metka=doizv_zakupki_meyer7'], cwd=DIR,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR=НАБОР, KC_CEL='meyer', KC_ZAKUPKI_DOBOR_OT='120e6', KC_ZAKUPKI_POTOKOV='2',
                              KC_EIS_INTERVAL='1.5', PYTHONIOENCODING='utf-8'))
выход.close()
time.sleep(40)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
