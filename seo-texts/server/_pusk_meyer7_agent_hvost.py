# -*- coding: utf-8 -*-
# Полный прогон Meyer, 10.10: перезапуск прохода агентов 120–500 млн («хвост»). Модель — МОДЕЛЬ ниже (владелец 10.10:
# хвост на Luna; Sol — KC_AGENT_HVOST_SOL=1, тогда пустые итоги Luna переделываются). Старый процесс хвоста гасится по метке, новый — с той же меткой
# (оркестратор видит его как свой фоновый шаг и ждёт), окружение — как у оркестратора для «kc_agent_glubokiy.py:хвост».
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
МЕТКА = '--shag=kc_agent_glubokiy.py_hvost'
МОДЕЛЬ = 'gpt-6-luna'
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*%s*' -and "
                    "$_.CommandLine -like '*--nabor=%s*' } | ForEach-Object { $_.ProcessId }" % (МЕТКА, НАБОР)],
                   capture_output=True, text=True, timeout=120)
pids = r.stdout.split()
for pid in pids:
    subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True, timeout=60)
time.sleep(8)
ЛОГ = os.path.join(DIR, 'konveyer_%s_kc_agent_glubokiy_хвост_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_agent_glubokiy.py'), '--nabor=' + НАБОР, МЕТКА], cwd=DIR,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', KC_BEZ_CHECKO='1',
                              KC_ZAKUPKI_OT='1e9', KC_POTOKOV_SHAGA='24', KC_AGENT_POTOKOV='30', KC_AGENT_XML_MIN='60',
                              KC_AGENT_OT='120e6', KC_AGENT_DO='500e6', KC_AGENT_FAYL='glubokiy-hvost.jsonl',
                              PROVIDER_MODEL=МОДЕЛЬ, PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna', PILOT_SNIMKI='1'))
выход.close()
time.sleep(40)
o = {'погашено': pids, 'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    o['хвост'] = open(ЛОГ, encoding='utf-8', errors='replace').read()[-500:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
