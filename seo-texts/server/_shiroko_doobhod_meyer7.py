# -*- coding: utf-8 -*-
# 12.10, владелец (скриншот as-agro.ru: info.as22@yandex.ru на страницах направлений, обход видел одну главную):
# широкий дообход — сайты, где обход увидел ≤2 своих страниц и ни одной почты: после ссылок «контакты/реквизиты/о компании»
# любые внутренние страницы главной, до 6 (kc_doobhod KC_DOOBHOD_SHIROKO=1). Ждёт конца возврата 380 (один писатель
# файла обхода), потом: дообход -> kc_dorazmetka (роли новым контактам) -> kc_audit («чей») -> копии на дроп.
# Лог: konveyer_meyer7_shiroko_*.log.
import glob, io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)

if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_shiroko_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri', '--metka=shiroko_meyer7'],
                             cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в,
                             stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                      'хвост': open(лог, encoding='utf-8', errors='replace').read()[-400:]}, ensure_ascii=False, indent=1))
    sys.exit(0)

import pilot_konveyer as PK  # noqa: E402


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def возврат_идёт():
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True,
                       text=True, errors='replace')
    return any('vozvrat2_' in x or '_vozvrat_sdelki_meyer7' in x for x in r.stdout.splitlines())


while возврат_идёт():
    time.sleep(60)
логи = sorted(glob.glob(os.path.join(DIR, 'konveyer_meyer7_vozvrat2_sdelki_*.log')))
п('возврат закончен:', 'ВОЗВРАТ ГОТОВ' in (open(логи[-1], encoding='utf-8', errors='replace').read() if логи else ''))
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=shiroko_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-700:].replace('\n', ' | '))
    return r.returncode


шаг('kc_doobhod.py', {'KC_DOOBHOD_SHIROKO': '1', 'KC_DOOBHOD_POTOKOV': '24'})
шаг('kc_dorazmetka.py')
шаг('kc_audit.py')
for ф in ('-kontakty.jsonl', '-audit.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ШИРОКО ГОТОВ')
