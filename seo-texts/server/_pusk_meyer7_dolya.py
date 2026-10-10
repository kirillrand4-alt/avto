# -*- coding: utf-8 -*-
# Полный прогон Meyer, 11.10: перезапуск ОДНОЙ доли обхода (kc_kontakty, KC_DOLYA=k/N) отдельным процессом. Зачем: при
# импорте verify_company каждый процесс берёт один случайный прокси из пула — доле 4 достался мёртвый (за 52 мин ни одной
# записи: все потоки ждут обогатитель, тот висит на socks). Новый процесс выберет прокси заново. Окружение — как у
# доли из обхода финала; журнал доли тот же (родитель сольёт его при выходе, остаток — следующий запуск обхода).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР, ДОЛЯ, ВСЕГО = 'meyer7', int(os.environ.get('DOLYA', '4')), int(os.environ.get('DOLEY', '6'))
МЕТКА = '--shag=kc_kontakty.py_dolya%d' % ДОЛЯ
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*%s' } | ForEach-Object { $_.ProcessId }" % МЕТКА],
                   capture_output=True, text=True, timeout=120)
старые = r.stdout.split()
for p in старые:
    subprocess.run(['taskkill', '/PID', p, '/F'], capture_output=True, timeout=60)
time.sleep(5)
env = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', KC_BEZ_CHECKO='1',
           KC_ZAKUPKI_OT='1e9', KC_EC='1', KC_EC_XML_OT='5e8', KC_EC_BEZ_MODELI='1', KC_LIMIT_MIN='25', KC_POTOKOV='96',
           KC_PROTSESSOV=str(ВСЕГО), KC_DOLYA='%d/%d' % (ДОЛЯ, ВСЕГО), KC_FAYL='%s-kontakty-dolya%d.jsonl' % (НАБОР, ДОЛЯ),
           KC_MODEL_PARALLEL='12', PROVIDER_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna', PILOT_SNIMKI='1')
лог = open(os.path.join(DIR, 'konveyer_%s_kc_kontakty_dolya%d_%s.log' % (НАБОР, ДОЛЯ, time.strftime('%d%m-%H%M'))), 'ab')
python = r'C:\Program Files\Python312\python.exe'
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'kc_kontakty.py'), '--nabor=' + НАБОР, МЕТКА], cwd=DIR, env=env,
                     creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=лог, stderr=subprocess.STDOUT, close_fds=False)
лог.close()
time.sleep(60)
print('===ИТОГ===')
print(json.dumps({'погашены': старые, 'pid': p.pid, 'жив': p.poll() is None}, ensure_ascii=False))
