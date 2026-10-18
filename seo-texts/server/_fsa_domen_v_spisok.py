# -*- coding: utf-8 -*-
# 18.10, владелец: «10686 можешь сразу серверный обход сделать?» — изготовители ФСА с корпоративной почтой (сайт = домен почты),
# новые для Meyer, без отсева и сделки -> в список meyer7 с этим сайтом и конвейер только по ним (обход, доизвлечение, роли,
# аудит, проверка сайта, опровергатели, паспорт, группы). Поиск сайта по названию не нужен. Ждёт конца _fsa_top_v_spisok.
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
    лог = os.path.join(DIR, 'fsa_domen_v_spisok_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_domen_v_spisok.py'), '--vnutri'], cwd=DIR,
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


while идут('_fsa_top_v_spisok'):
    time.sleep(60)
ПОРОГ = 0.0
БЕСПЛ = {'mail.ru','bk.ru','inbox.ru','list.ru','yandex.ru','ya.ru','gmail.com','rambler.ru','yahoo.com','icloud.com','outlook.com',
         'hotmail.com','internet.ru','yandex.com','mail.com','lenta.ru','autorambler.ru','ro.ru','myrambler.ru','km.ru','narod.ru','yandex.by','tut.by'}
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
os.environ.update(w.env_шага('kc_kontakty.py'))
import kc_kontakty as KK  # noqa: E402
import meyer7_inn_poisk as P  # noqa: E402
import zamok  # noqa: E402

# 1) изготовители из полной выкачки ФСА (fsa-meyer-izg.jsonl), без отсеянных (fsa-meyer-otsev.jsonl «нет»)
отсев = {}
for s_ in io.open(os.path.join(DIR, 'fsa-meyer-otsev.jsonl'), encoding='utf-8', errors='replace'):
    try:
        y_ = json.loads(s_); отсев[y_['инн']] = y_.get('ответ')
    except (ValueError, KeyError):
        pass
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
есть = set()
for р, v in сп.items():
    if isinstance(v, dict):
        есть |= set(v)
есть |= {json.loads(s)['инн'] for s in io.open(os.path.join(DIR, 'meyer7-inn-sayt.jsonl'), encoding='utf-8') if s.strip()}
кп = collections.Counter()
for s_ in io.open(os.path.join(DIR, 'fsa-meyer-izg.jsonl'), encoding='utf-8', errors='replace'):
    for a in set(json.loads(s_).get('почты') or []):
        кп[a] += 1
отобр = []
for s_ in io.open(os.path.join(DIR, 'fsa-meyer-izg.jsonl'), encoding='utf-8', errors='replace'):
    z = json.loads(s_)
    try:
        выр_ = float(z.get('выручка') or 0)
    except ValueError:
        выр_ = 0.0
    if отсев.get(z['инн']) == 'нет' or z['инн'] in есть or z.get('сделка_meyer') or выр_ < ПОРОГ:
        continue
    z['сам'] = bool(z.get('сам_заявитель'))
    дом = sorted({a.split('@')[-1] for a in z.get('почты') or [] if a.split('@')[-1] not in БЕСПЛ and кп[a] < 5})
    if not дом:
        continue
    z['домен'] = дом[0]
    отобр.append(z)
п('ФСА: с корпоративной почтой (сайт по домену), новых для Meyer, без сделки и отсева: %d' % len(отобр))

# 3) DaData + наша база
dd = P.DaData()
обз = {}
нужны = {z['инн'] for z in отобр}
c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
for i, выр, сайт in c.execute('select inn, revenue_rub, sites from obzvon'):
    if str(i) in нужны:
        обз[str(i)] = (float(выр or 0), сайт or '')
c.close()
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
for i, выр, сайт in c.execute('select inn, revenue_rub, site from companies'):
    if str(i) in нужны and str(i) not in обз:
        обз[str(i)] = (float(выр or 0), сайт or '')
c.close()

# 4) в список
СП = os.path.join(DIR, 'meyer7-spisok.json')
ключи = []
with zamok.замок(СП):
    сп = zamok.прочитать(СП)
    shutil.copyfile(СП, СП + '.bak-fsa3-' + time.strftime('%d%m-%H%M'))
    for z in отобр:
        i = z['инн']
        if i in сп['компании'] or i in (сп.get('снято') or {}):
            continue
        к = (dd.найти('id', i) or [{}])[0]
        if к.get('статус') and к['статус'] != 'ACTIVE':
            continue
        выр, сайт = обз.get(i, (0.0, ''))
        сайт = (re.split(r'[\s,;|]+', сайт.strip()) or [''])[0] or z['домен']
        сп['компании'][i] = {
            'inn': i, 'имя': к.get('имя') or z['имя'], 'регион': к.get('регион') or '', 'сайт': ('https://' + сайт) if сайт and '://' not in сайт else сайт,
            'осн': к.get('оквэд') or '', 'все': [], 'сегм': 'реестр деклараций ФСА: ' + (z['продукция'][0][:60] if z['продукция'] else ''), 'сегм_как': 'по сайту',
            'выручка': выр, 'выручка_откуда': 'наша база' if выр else 'неизвестна', 'запросы': [],
            'откуда': 'реестр деклараций ФСА 18.10 (сайт — домен почты из декларации): %s (деклараций %d, последняя %s%s)' % (
                z['продукция'][0][:120], z['деклараций'], z['последняя'], '; заявитель — сам изготовитель' if z['сам'] else ''),
            'в_нашей_базе': 'да' if i in обз else 'нет', 'в_реестре': 'нет', 'огрн': к.get('огрн') or '',
            'примечание': ('руководитель: %s' % к['руководитель']) if к.get('руководитель') else ''}
        ключи.append(i)
    zamok.записать_атомарно(СП, сп)
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-fsa3-inn.txt')
with io.open(СПИСОК_ИНН, 'w', encoding='utf-8') as f:
    f.write('\n'.join(ключи) + '\n')
    f.flush()
    os.fsync(f.fileno())
п('в список добавлено', len(ключи), '| с сайтом из нашей базы', sum(1 for i in ключи if сп['компании'][i]['сайт']))


# 5) конвейер только по ним (один писатель файла обхода: ждём чужие конвейеры)
while идут('_dobavit_dopoisk') or идут('_pusk_meyer7_pereobhod') or идут('_zenka107_razbor'):
    time.sleep(60)


def шаг(файл, доп=None):
    env = dict(w.env_шага(файл), **(доп or {}))
    t0 = time.time()
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=fsa3_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode


ТОЛЬКО = {'KC_TOLKO_INN': СПИСОК_ИНН}
if ключи:
    шаг('kc_kontakty.py')
    шаг('kc_doizvlech.py')
    шаг('kc_doizvlech_pochty.py', ТОЛЬКО)
    шаг('kc_skrytye.py', dict(ТОЛЬКО, KC_SKRYTYE_PROBA='0'))
    шаг('kc_doobhod.py', ТОЛЬКО)
    шаг('kc_doobhod.py', dict(ТОЛЬКО, KC_DOOBHOD_SHIROKO='1'))
    шаг('kc_dorazmetka.py')
    шаг('kc_audit.py')
    шаг('kc_sayt_proverka.py')
    шаг('kc_oproverzhenie.py')
    шаг('pilot_pasport.py')
    шаг('kc_gruppy.py', {'PROVIDER_MODEL': 'gpt-6-luna'})
for ф in ('-kontakty.jsonl', '-spisok.json', '-audit.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-pasport.jsonl', '-gruppy.jsonl'):
    try:
        shutil.copyfile(os.path.join(DIR, 'meyer7' + ф), os.path.join(PK.ДРОП, 'meyer7' + ф))
    except Exception as e:  # noqa: BLE001
        п('копия', ф, repr(e)[:80])
for ф in ('meyer7-fsa3-inn.txt',):
    shutil.copyfile(os.path.join(DIR, ф), os.path.join(PK.ДРОП, ф))
п('ФСА ПО ДОМЕНУ ПОЧТЫ ГОТОВО')
