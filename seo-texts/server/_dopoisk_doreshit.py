# -*- coding: utf-8 -*-
# 13.10: допоиск 12.10 — по ~60 открытым сайтам модель не ответила (шлюз 503). Дорешить (режим --model резюмируемый: решённые
# домены пропускаются), сводка --itog; если появились новые «да» — дождаться конца разбора Зенки-107 (один писатель файла
# обхода) и добавить их тем же скриптом, что 921 (_dobavit_dopoisk_meyer7.py: в список + конвейер контактов только по новым).
# Лог: konveyer_meyer7_dopoisk_doreshit_*.log.
import io, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna',
                   'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'KC_MODEL_PARALLEL': '32', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_dopoisk_doreshit_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
РЕШ = os.path.join(DIR, 'meyer7-dopoisk-reshenie.jsonl')


def да_домены():
    return {json.loads(s)['домен'] for s in io.open(РЕШ, encoding='utf-8') if s.strip() and '"решение": "да"' in s}


было_да = да_домены()
for режим in ('--model', '--itog'):
    t0 = time.time()
    r = subprocess.run([PK.питон('kc_kontakty.py'), '-u', os.path.join(DIR, 'meyer7_dopoisk.py'), режим], cwd=DIR,
                       env=dict(w.env_шага('kc_kontakty.py'), PYTHONIOENCODING='utf-8'), capture_output=True, text=True,
                       errors='replace')
    п(режим, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-1200:])
нов = да_домены() - было_да
п('новых «да»', len(нов), sorted(нов)[:20])
if нов:
    def идут(метка):
        r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True,
                           text=True, errors='replace')
        return any(метка in x for x in r.stdout.splitlines())
    while идут('_zenka107_razbor'):
        time.sleep(60)
    п('разбор Зенки-107 закончен — добавляю')
    r = subprocess.run([sys.executable, '-u', os.path.join(DIR, '_dobavit_dopoisk_meyer7.py'), '--vnutri'], cwd=DIR,
                       capture_output=True, text=True, errors='replace')
    п('добавление код', r.returncode, '|', (r.stdout + r.stderr)[-2500:])
п('ДОРЕШЕНИЕ ДОПОИСКА ГОТОВО')
