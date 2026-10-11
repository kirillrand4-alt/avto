# -*- coding: utf-8 -*-
# 11.10 22:15: хвост meyer7 после шагов оркестратора «после агентов». Сам ждёт отметки «конец» в meyer7-konveyer.json
# (файл обхода пишет только оркестратор), потом последовательно, одним писателем:
#   0) Крелит (6140040981): сайт возвращён на krelit.ru (агент поставил страницу каталога regtorg, обход 21:52 взял её) —
#      прежняя запись обхода по krelit.ru — снова последней;
#   1) kc_kontakty — обход возвращённых сайтов (АУРАТ auratlab.ru, МАШИНЕРИ emr52.ru, КАМАПЭК kamapek.ru);
#   2) список ИНН, обойдённых заново (последняя запись без «доизвлечено»: прежние записи доизвлечение пометило все);
#   3) доизвлечение для них: номера (kc_doizvlech), почты (kc_doizvlech_pochty), спрятанные (kc_skrytye), дообход
#      (kc_doobhod) — обход kc_kontakty этих разборщиков не вызывает;
#   4) kc_dorazmetka (роли новым контактам), kc_sayt_proverka (возвращённые сайты), копии на дроп.
# Лог: konveyer_meyer7_hvost_posle_*.log.
import io, json, os, re, shutil, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({  # окружение оркестратора финала (как _pusk_meyer7_final_s_obhoda.py)
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6',
    'PILOT_SAYTY_MAX': '24000', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)

if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'konveyer_meyer7_hvost_posle_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri', '--metka=hvost_posle_meyer7'],
                             cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в,
                             stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог),
                      'хвост': open(лог, encoding='utf-8', errors='replace').read()[-400:]}, ensure_ascii=False, indent=1))
    sys.exit(0)

import pilot_konveyer as PK  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

КОНВ = os.path.join(DIR, 'meyer7-konveyer.json')
КОНТ = os.path.join(DIR, 'meyer7-kontakty.jsonl')
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-hvost-inn.txt')


def п(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


while True:
    try:
        if json.load(io.open(КОНВ, encoding='utf-8')).get('конец'):
            break
    except Exception:  # noqa: BLE001
        pass
    time.sleep(60)
п('оркестратор закончил')

# 0) Крелит: прежняя запись по krelit.ru — последней
посл, по_сайту = None, None
for s in io.open(КОНТ, encoding='utf-8', errors='replace'):
    if '"6140040981"' not in s:
        continue
    try:
        з = json.loads(s)
    except ValueError:
        continue
    if з.get('inn') == '6140040981':
        посл = з
        if MN.домен(з.get('сайт') or '') == 'krelit.ru':
            по_сайту = з
if посл and по_сайту and MN.домен(посл.get('сайт') or '') != 'krelit.ru':
    with io.open(КОНТ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(dict(по_сайту, возврат_сайта='11.10: krelit.regtorg.ru — каталог'), ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    п('Крелит: прежняя запись по krelit.ru — последней')
else:
    п('Крелит: без изменений', посл and посл.get('сайт'), bool(по_сайту))

w = PK.Волны()


def шаг(файл, доп=None, env_шага=None):
    env = dict(w.env_шага(env_шага or файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=hvost_posle_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-700:].replace('\n', ' | '))
    return r.returncode


шаг('kc_kontakty.py')

# 2) кого обошли заново
посл = {}
for s in io.open(КОНТ, encoding='utf-8', errors='replace'):
    try:
        з = json.loads(s)
    except ValueError:
        continue
    if з.get('inn'):
        посл[з['inn']] = з
инн = sorted(i for i, з in посл.items() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('доизвлечено'))
with io.open(СПИСОК_ИНН, 'w', encoding='utf-8') as f:
    f.write('\n'.join(инн) + '\n')
    f.flush()
    os.fsync(f.fileno())
п('обойдены заново (без доизвлечения):', len(инн))
del посл

ТОЛЬКО = {'KC_TOLKO_INN': СПИСОК_ИНН}
шаг('kc_doizvlech.py')
шаг('kc_doizvlech_pochty.py', ТОЛЬКО)
шаг('kc_skrytye.py', dict(ТОЛЬКО, KC_SKRYTYE_PROBA='0'))
шаг('kc_doobhod.py', ТОЛЬКО)
шаг('kc_dorazmetka.py')
шаг('kc_sayt_proverka.py')
for ф in ('-kontakty.jsonl', '-sayt-proverka.jsonl', '-spisok.json'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ХВОСТ ГОТОВ')
