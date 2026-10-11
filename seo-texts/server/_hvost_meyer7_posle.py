# -*- coding: utf-8 -*-
# 11.10 22:15: хвост meyer7 после шагов оркестратора «после агентов». Сам ждёт отметки «конец» в meyer7-konveyer.json
# (файл обхода пишет только оркестратор), потом последовательно, одним писателем:
#   0) рассинхрон «сайт в списке ≠ сайт последней записи» (70 комп.): сайт из баз, раньше отклонённый, — прежний сайт
#      в списке; иначе старая запись по сайту списка — снова последней (Крелит, slavoliya.ru, вердикты «та же»);
#   1) kc_kontakty — обход возвращённых сайтов (АУРАТ auratlab.ru, МАШИНЕРИ emr52.ru, КАМАПЭК kamapek.ru);
#   2) список ИНН, обойдённых заново (последняя запись без «доизвлечено»: прежние записи доизвлечение пометило все);
#   3) доизвлечение для них: номера (kc_doizvlech), почты (kc_doizvlech_pochty), спрятанные (kc_skrytye), дообход
#      (kc_doobhod) — обход kc_kontakty этих разборщиков не вызывает;
#   4) kc_dorazmetka (роли новым контактам), kc_audit + kc_audit2 (аудит оркестратора упал 00:53), kc_sayt_proverka
#      (возвращённые сайты), копии на дроп.
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

# 0) рассинхрон «сайт в списке ≠ сайт последней записи обхода» (22:41: 70 компаний): обход не обходит пару (ИНН, домен),
#    которая уже есть в старых записях. (а) сайт из наших баз с прежним вердиктом проверки «другая» (pilot_sayty_baz
#    исключал только текущий отклонённый домен) — в списке вернуть прежний сайт; (б) иначе — старая запись по сайту
#    списка снова последней (Крелит, slavoliya.ru с ИНН, вердикты «та же»).
import zamok  # noqa: E402
СП = os.path.join(DIR, 'meyer7-spisok.json')
вер = {}
for s in io.open(os.path.join(DIR, 'meyer7-sayt-proverka.jsonl'), encoding='utf-8', errors='replace'):
    try:
        x = json.loads(s)
    except ValueError:
        continue
    вер[(x.get('inn'), MN.домен(x.get('сайт') or ''))] = x.get('итог')
посл_дом, поз_дом = {}, {}
with open(КОНТ, 'rb') as f:
    while True:
        поз = f.tell()
        s = f.readline()
        if not s:
            break
        try:
            з = json.loads(s)
        except ValueError:
            continue
        i = з.get('inn')
        if i:
            д = MN.домен(з.get('сайт') or '')
            посл_дом[i] = д
            поз_дом[(i, д)] = поз
сп = zamok.прочитать(СП)['компании']
вернуть, переложить = {}, []
for i, к in сп.items():
    д = MN.домен(к.get('сайт') or '')
    дз = посл_дом.get(i)
    if not д or not дз or д == дз or д.endswith(дз) or дз.endswith(д):
        continue
    if str(к.get('сайт_откуда') or '').startswith('наша база') and вер.get((i, д)) == 'другая' and к.get('сайт_был') is not None:
        вернуть[i] = к.get('сайт_был') or ''
    elif (i, д) in поз_дом and вер.get((i, д)) != 'другая':
        переложить.append((i, поз_дом[(i, д)]))
if вернуть:
    with zamok.замок(СП):
        сп_ = zamok.прочитать(СП)
        for i, был in вернуть.items():
            к = сп_['компании'][i]
            к['сайт_из_баз_снят'] = к.get('сайт')
            к['сайт'] = был
            к['сайт_откуда'] = 'возврат 11.10: сайт из баз раньше отклонён проверкой («другая»)'
        zamok.записать_атомарно(СП, сп_)
if переложить:
    with open(КОНТ, 'rb') as f, io.open(КОНТ, 'a', encoding='utf-8') as вых:
        for i, поз in переложить:
            f.seek(поз)
            з = json.loads(f.readline())
            вых.write(json.dumps(dict(з, возврат_записи='11.10: запись по сайту из списка — снова последней'),
                                 ensure_ascii=False) + '\n')
        вых.flush()
        os.fsync(вых.fileno())
п('рассинхрон: в списке возвращён прежний сайт', len(вернуть), '| старая запись снова последней', len(переложить))
del посл_дом, поз_дом, сп

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
# 12.10: kc_audit оркестратора упал на почтах без ключа «номер» (KeyError, 00:53; исправлено), аудит-2 по его неполному
# выходу остановлен — оба здесь, после всех добавок (и хвостовые контакты получают «чей»)
шаг('kc_audit.py')
шаг('kc_audit2.py')
шаг('kc_sayt_proverka.py')
for ф in ('-kontakty.jsonl', '-sayt-proverka.jsonl', '-spisok.json', '-audit.jsonl', '-audit2.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
п('ХВОСТ ГОТОВ')
