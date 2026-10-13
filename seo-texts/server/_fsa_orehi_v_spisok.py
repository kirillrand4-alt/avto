# -*- coding: utf-8 -*-
# 13.10, владелец: «полный прогон как делал с общей базой сделай по ним за ночь» — изготовители орехов/сухофруктов из
# реестра деклараций ФСА (fsa_pilot_orehi.py → fsa-orehi.jsonl). Ночью:
#   1) дождаться конца пробы; изготовители РФ (ИНН), которых нет в списке meyer7 (все разделы) и нет активной сделки Meyer;
#   2) модель: сам продукт — орехи/сухофрукты/семечки/ядра (переработчик), а не кондитерка/выпечка/сыр «с орехом»;
#   3) DaData findById — название, регион, ОКВЭД; выручка — obzvon/enrich;
#   4) в список (под замком, бэкап): ключ ИНН, сегмент «орехи, сухофрукты (реестр ФСА)», откуда — продукция из декларации;
#   5) конвейер только по ним: поиск сайта, обход, доизвлечение, скрытые, дообход (и широкий), роли, аудит, проверка сайта,
#      опровергатели, паспорт, группы; копии на дроп. Итог отбора — fsa-orehi-otbor.jsonl. Лог: fsa_orehi_v_spisok_*.log.
import collections, io, json, os, re, shutil, sqlite3, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({
    'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'POISK_REGIONY_SVERKI': 'все', 'PILOT_VOLNY': '1',
    'KC_EC': '1', 'KC_EC_XML_OT': '5e8', 'KC_EC_BEZ_MODELI': '1', 'KC_LIMIT_MIN': '25',
    'KC_POTOKOV': '96', 'KC_MODEL_PARALLEL': '32', 'KC_PROTSESSOV': '6', 'PILOT_SAYTY_MAX': '0', 'KC_AGENT_XML_MIN': '60',
    'PILOT_MODEL': 'gpt-6-luna', 'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_orehi_v_spisok_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_orehi_v_spisok.py'), '--vnutri'], cwd=DIR,
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


while идут('fsa_pilot_orehi'):
    time.sleep(60)
п('проба ФСА закончена')
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
os.environ.update(w.env_шага('kc_kontakty.py'))
import kc_kontakty as KK  # noqa: E402
import meyer7_inn_poisk as P  # noqa: E402
import zamok  # noqa: E402

# 1) изготовители
декл = [json.loads(s) for s in io.open(os.path.join(DIR, 'fsa-orehi.jsonl'), encoding='utf-8') if s.strip()]
изг = collections.OrderedDict()
for x in декл:
    i = re.sub(r'\D', '', x.get('manufacterInn') or '')
    if len(i) not in (10, 12):
        continue
    z = изг.setdefault(i, {'инн': i, 'имя': x.get('manufacterName') or '', 'адрес': (x.get('manufacterAddress') or '')[:200], 'продукция': [],
                           'деклараций': 0, 'последняя': '', 'сам': False, 'декл': []})
    z['деклараций'] += 1
    z['последняя'] = max(z['последняя'], x.get('declDate') or '')
    пр = re.sub(r'\s+', ' ', x.get('productFullName') or '')[:160]
    if пр and пр not in z['продукция'] and len(z['продукция']) < 4:
        z['продукция'].append(пр)
    z['сам'] = z['сам'] or re.sub(r'\D', '', x.get('applicantInn') or '') == i
    z['декл'].append(x.get('declNumber') or '')
сп = json.load(io.open(os.path.join(DIR, 'meyer7-spisok.json'), encoding='utf-8'))
есть = set()
for р, v in сп.items():
    if isinstance(v, dict):
        есть |= set(v)
есть |= {json.loads(s)['инн'] for s in io.open(os.path.join(DIR, 'meyer7-inn-sayt.jsonl'), encoding='utf-8') if s.strip()}
сд = {}
for s in io.open(r'C:\seostat\drop\drop-storage\meyer7-sdelki-aktivnye.tsv', encoding='utf-8').read().splitlines()[1:]:
    ч = s.split('\t')
    if ч and ч[0].isdigit():
        сд[ч[0]] = ч[1] if len(ч) > 1 else ''
кандидаты = [z for i, z in изг.items() if i not in есть and i not in сд]
п('деклараций', len(декл), '| изготовителей РФ', len(изг), '| новых без сделки', len(кандидаты))

# 2) модель: переработчик орехов/сухофруктов?
ОТБОР = os.path.join(DIR, 'fsa-orehi-otbor.jsonl')
решено = {}
if os.path.exists(ОТБОР):
    for s in io.open(ОТБОР, encoding='utf-8'):
        try:
            y = json.loads(s)
            решено[y['инн']] = y
        except (ValueError, KeyError):
            pass
ПР = ('По продукции из деклараций реши для каждого изготовителя: его СОБСТВЕННЫЙ продукт — орехи, ядра орехов, арахис, '
      'семечки/ядро подсолнечника и тыквы, сухофрукты (изюм, курага, чернослив, финики, цукаты), ореховые пасты/урбеч, смеси '
      'орехов и сухофруктов — «да»; кондитерка, выпечка, шоколад, сыр, колбаса, салаты, мёд, пряности и прочее, где орех лишь в '
      'составе или в названии, — «нет».\nОтвет — ТОЛЬКО JSON-массив: [{{"n":номер,"ответ":"да|нет"}}]\n\n{б}')
задачи = [z for z in кандидаты if z['инн'] not in решено]
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def пачка(п_):
    б = '\n'.join('%d. %s' % (j, ' | '.join(z['продукция'])[:400]) for j, z in enumerate(п_, 1))
    о = KK.модель(ПР.format(б=б), True) or {}
    return [(z, (о.get(j) or {}).get('ответ') or '') for j, z in enumerate(п_, 1)]


with ThreadPoolExecutor(6) as ex:
    for рез in ex.map(пачка, [задачи[k:k + 25] for k in range(0, len(задачи), 25)]):
        with io.open(ОТБОР, 'a', encoding='utf-8') as f:
            for z, о in рез:
                y = dict(z, ответ=о)
                решено[z['инн']] = y
                f.write(json.dumps(y, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
отобр = [решено[z['инн']] for z in кандидаты if решено.get(z['инн'], {}).get('ответ') == 'да']
п('модель: переработчиков орехов/сухофруктов', len(отобр), 'из', len(кандидаты), '| без ответа',
  sum(1 for z in кандидаты if not решено.get(z['инн'], {}).get('ответ')))

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
    shutil.copyfile(СП, СП + '.bak-fsa-' + time.strftime('%d%m-%H%M'))
    for z in отобр:
        i = z['инн']
        if i in сп['компании'] or i in (сп.get('снято') or {}):
            continue
        к = (dd.найти('id', i) or [{}])[0]
        if к.get('статус') and к['статус'] != 'ACTIVE':
            continue
        выр, сайт = обз.get(i, (0.0, ''))
        сайт = (re.split(r'[\s,;|]+', сайт.strip()) or [''])[0]
        сп['компании'][i] = {
            'inn': i, 'имя': к.get('имя') or z['имя'], 'регион': к.get('регион') or '', 'сайт': ('https://' + сайт) if сайт and '://' not in сайт else сайт,
            'осн': к.get('оквэд') or '', 'все': [], 'сегм': 'орехи, сухофрукты — переработка (реестр деклараций ФСА)', 'сегм_как': 'по сайту',
            'выручка': выр, 'выручка_откуда': 'наша база' if выр else 'неизвестна', 'запросы': [],
            'откуда': 'реестр деклараций ФСА 13.10: %s (деклараций %d, последняя %s%s)' % (
                z['продукция'][0][:120], z['деклараций'], z['последняя'], '; заявитель — сам изготовитель' if z['сам'] else ''),
            'в_нашей_базе': 'да' if i in обз else 'нет', 'в_реестре': 'нет', 'огрн': к.get('огрн') or '',
            'примечание': ('руководитель: %s' % к['руководитель']) if к.get('руководитель') else ''}
        ключи.append(i)
    zamok.записать_атомарно(СП, сп)
СПИСОК_ИНН = os.path.join(DIR, 'meyer7-fsa-inn.txt')
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
    r = subprocess.run([PK.питон(файл), '-u', os.path.join(DIR, файл), '--metka=fsa_' + файл[:-3]], cwd=DIR,
                       env=env, capture_output=True, text=True, errors='replace')
    п(файл, 'код', r.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', (r.stdout + r.stderr)[-500:].replace('\n', ' | '))
    return r.returncode


ТОЛЬКО = {'KC_TOLKO_INN': СПИСОК_ИНН}
if ключи:
    шаг('pilot_sayty_dobor.py', ТОЛЬКО)
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
for ф in ('fsa-orehi-otbor.jsonl', 'meyer7-fsa-inn.txt'):
    shutil.copyfile(os.path.join(DIR, ф), os.path.join(PK.ДРОП, ф))
п('ФСА ОРЕХИ В СПИСКЕ ГОТОВО')
