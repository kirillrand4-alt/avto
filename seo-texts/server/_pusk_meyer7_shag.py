# -*- coding: utf-8 -*-
# Полный прогон Meyer: один шаг конвейера отдельным процессом с меткой волн (оркестратор видит его и второй не запускает).
# Шаг и модель — в ШАГ/МОДЕЛЬ ниже (правится перед запуском). 10.10: kc_sayt_proverka упал на гонке доставки.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ШАГ, МОДЕЛЬ = 'pilot_pasport.py', 'gpt-5.6-luna'
# 11.10: паспорт шёл 39 компаний/мин в 8 потоков (~10,9 тыс. к разбору = 4,5 ч). Luna 6 в 24 потока (06:06–06:43) дала
# 60/мин, но на одних и тех же 14 компаниях вдвое меньше оборудования линий / контроля качества / мощностей, чем Luna 5.6
# -> обратно Luna 5.6 (модель site_facts по умолчанию), 24 потока; паспорта окна Luna 6 — собрать заново (сливаются).
# 07:42: обрывы 10054 — тело одним куском; pilot_pasport шлёт кусками (PASPORT_KUSKAMI=1 по умолчанию)
# 10:30: догон — «вне списка» без паспорта из-за имени файла кэша (4471) и 196 неудачных пересборов окна Luna 6
ДОП_ENV = {'FACTS_MODEL': 'gpt-5.6-luna', 'PASPORT_POTOKOV': '24', 'PASPORT_PEREDELAT_SBOI': '2026-10-11T06:43'}
ЛОГ = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, ШАГ[:-3], time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if ШАГ == 'pilot_pasport.py':  # паспорт (site_facts -> gen_provider -> anthropic) — только питон панели 3.11
    python = r'C:\Program Files\Python311\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, ШАГ), '--nabor=' + НАБОР, '--shag=' + ШАГ], cwd=DIR,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', KC_BEZ_CHECKO='1',
                              KC_POTOKOV_SHAGA='24', PROVIDER_MODEL=МОДЕЛЬ, PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna', **ДОП_ENV))
выход.close()
time.sleep(30)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-400:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
