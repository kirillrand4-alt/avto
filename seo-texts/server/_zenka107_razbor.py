# -*- coding: utf-8 -*-
# 13.10: 107 защищённых сайтов (из 215, отданных Зенке при переобходе 12.10) — Зенка принесла страницы после 11:25,
# когда разбор долями уже шёл (по ИНН по порядку) → эти страницы не разобраны. Разбор kc_skrytye режим zenka только по ним
# (KC_TOLKO_INN, новая отметка KC_SKRYTYE_ZENKA_OT), один писатель файла обхода; затем доразметка ролей и аудит; копии на дроп.
# Лог: konveyer_meyer7_zenka107_*.log.
import json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
os.environ.update({'KC_NABOR': 'meyer7', 'POISK_NABOR': 'meyer7', 'PYTHONIOENCODING': 'utf-8'})
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_zenka107_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR, creationflags=0x08 | 0x200,
                             stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-800:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
СПИСОК = os.path.join(DIR, 'meyer7-zenka215-pozdno.txt')


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=zenka107_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, (доп or {}).get('KC_SKRYTYE_REZHIM', ''), 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|',
      (r.stdout + r.stderr)[-700:].replace('\n', ' | '))
    return r.returncode


п('компаний в списке', len(open(СПИСОК, encoding='utf-8').read().split()))
шаг('kc_skrytye.py', {'KC_SKRYTYE_REZHIM': 'zenka', 'KC_SKRYTYE_ZENKA_OT': '2026-10-13 04:30', 'KC_SKRYTYE_PROBA': '0',
                      'KC_TOLKO_INN': СПИСОК})
шаг('kc_dorazmetka.py')
шаг('kc_audit.py')
for ф in ('-kontakty.jsonl', '-audit.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ЗЕНКА 107 ГОТОВО')
