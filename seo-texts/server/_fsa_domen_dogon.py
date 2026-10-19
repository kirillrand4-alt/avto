# -*- coding: utf-8 -*-
# 19.10: догон конвейера «ФСА по домену почты» (_fsa_domen_v_spisok) — 19.10 ~05:00 кончился баланс провайдера на шаге
# kc_sayt_proverka (и начале kc_oproverzhenie). Неответы модели эти шаги не пишут -> повторный проход доделывает только их.
# Ждёт конца _fsa_domen_v_spisok, затем проверка сайта, опровергатели, паспорт, группы (всё резюмируемо).
import collections, io, json, os, re, shutil, sqlite3, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '48', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6', 'PILOT_SAYTY_MAX': '0', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_domen_dogon_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_domen_dogon.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-500:]},
                     ensure_ascii=False))
    sys.exit(0)


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def идут(метка):
    r = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'CommandLine'], capture_output=True, text=True, errors='replace')
    return any(метка in x for x in r.stdout.splitlines())


while идут('_fsa_domen_v_spisok'):
    time.sleep(60)
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=fsa3d_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode


шаг('kc_sayt_proverka.py')
шаг('kc_oproverzhenie.py')
шаг('pilot_pasport.py')
шаг('kc_gruppy.py', {'PROVIDER_MODEL': 'gpt-6-luna'})
for ф in ('-sayt-proverka.jsonl', '-oprov.jsonl', '-pasport.jsonl', '-gruppy.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ДОГОН ФСА ПО ДОМЕНУ ГОТОВ')
