# -*- coding: utf-8 -*-
# 12.10, владелец: «теперь можешь скачать то, что я говорил отложить, сервер пока свободен» — допоиск по сайтам выдачи
# («неясно» + «нет» по сниппету): 4 доли скачивания (вывод — в файлы), потом решение модели по тексту, сводка.
# Лог: konveyer_meyer7_dopoisk_*.log. Файл обхода и список не пишутся.
import glob, json, os, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_MODEL': 'gpt-6-luna',
                   'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'KC_MODEL_PARALLEL': '32', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_dopoisk_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(40)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
ДОЛЕЙ = 4
доли, логи = [], []
for k in range(ДОЛЕЙ):
    л = os.path.join(DIR, 'konveyer_meyer7_dopoisk_skachat_%s_d%d.log' % (time.strftime('%d%m-%H%M'), k))
    логи.append(л)
    with open(л, 'wb') as в:
        доли.append(subprocess.Popen([PK.питон('kc_kontakty.py'), '-u', os.path.join(DIR, 'meyer7_dopoisk.py'), '--skachat'], cwd=DIR,
                                     stdout=в, stderr=subprocess.STDOUT,
                                     env=dict(os.environ, ZS_DOLYA='%d/%d' % (k, ДОЛЕЙ), ZS_POTOKOV='48')))
for k, д in enumerate(доли):
    д.wait()
    п('скачивание доля', k, 'код', д.returncode, '|', open(логи[k], encoding='utf-8', errors='replace').read()[-200:].replace('\n', ' | '))
for режим in ('--model', '--itog'):
    t0 = time.time()
    r = subprocess.run([PK.питон('kc_kontakty.py'), '-u', os.path.join(DIR, 'meyer7_dopoisk.py'), режим], cwd=DIR,
                       env=dict(w.env_шага('kc_kontakty.py'), PYTHONIOENCODING='utf-8'), capture_output=True, text=True,
                       errors='replace')
    п(режим, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-1500:])
п('ДОПОИСК ГОТОВ')
