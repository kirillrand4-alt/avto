# -*- coding: utf-8 -*-
# 19.10, база холодного прозвона (Кемеровская/Томская/Омская), этап 2, группы «профиль» и «факты» (буква p). Только уже
# собранное (дроп + базы сервера), ничего не качаем, провайдера не зовём. Фильтр — ИНН из hz\hz-univers.jsonl.
# ПРОФИЛЬ (одна запись на ИНН и источник): obzvon-index.db; enrich.db companies и requisites; kc1-spisok.json и
# meyer7-spisok.json (разделы «компании», «на_решение»); fsa-meyer-dadata.jsonl; fsa-meyer-checko.jsonl + hz\hz-checko.jsonl
# (карточка checko, итог ok); PARK-OKVED-2S / PARK-CHECKO-2S / PARK-DADATA-2S.jsonl; master-base.sqlite;
# newsco_targets.jsonl.gz; fsa-meyer-izg.jsonl (имя, адрес заявителя); cerber-meyer-inn2/-inn.jsonl (имя и ОКВЭД ЕГРЮЛ);
# и для каждого ИНН вселенной — «ФНС (доход 2025)». Имя ОКВЭД по коду добирается из словаря тех же файлов.
# ФАКТЫ: сделки — kc-sc-sdelki-0910.csv (номер, воронка, стадия), sdelki-vse-1410.json (то, чего нет в csv: Meyer и хвост
# СЦ), meyer7-sdelki-aktivnye.tsv (активные Meyer с номером), sdelki-inn.json (стоп-лист панели, если активной сделки иначе
# не видно); kc-sdelki-aktivnye.tsv и bitrix-kc.json целиком покрыты csv — дублей не пишем. Декларации ФСА —
# fsa-meyer-izg.jsonl + id из fsa-meyer-kontakty2.jsonl (ссылка на декларацию). Цербер — cerber-meyer.jsonl, ИНН только
# подтверждённый (cerber-meyer-inn2, «Цербер подтвердил по ИНН»). Паспорт производства — kc1/meyer7-pasport.jsonl (без
# «низкой» уверенности; один на ИНН, богаче). Книга продаж — Company.xlsx, лист «Исходники», свод по ИНН.
# Выход: C:\sender\server\hz\hz-profil-p.jsonl, hz-fakty-p.jsonl (атомарная замена, fsync).
import collections, csv, datetime, gzip, html, io, json, os, re, sqlite3, time
csv.field_size_limit(10 ** 9)
D = r'C:\seostat\drop\drop-storage'
S = r'C:\sender\server'
HZ = os.path.join(S, 'hz')
ПРОФ = os.path.join(HZ, 'hz-profil-p.jsonl')
ФАКТ = os.path.join(HZ, 'hz-fakty-p.jsonl')
ФНС_URL = 'https://www.nalog.gov.ru/opendata/7707329152-revexp/'
ЦЕРБЕР_URL = 'https://cerberus.vetrf.ru/cerberus/certified/pub'
ФСА_URL = 'https://pub.fsa.gov.ru/rds/declaration/view/%s/common'
DADATA_СТАТУС = {'ACTIVE': 'Действующая', 'LIQUIDATING': 'Ликвидируется', 'LIQUIDATED': 'Ликвидирована',
                 'BANKRUPT': 'Банкротство', 'REORGANIZING': 'В процессе реорганизации'}
СТАТ = collections.defaultdict(collections.Counter)
t0 = time.time()


def п(*a):
    print(time.strftime('%d.%m %H:%M:%S'), *a, flush=True)


def jl(путь, gz=False):
    if not os.path.exists(путь):
        СТАТ['нет файла'][os.path.basename(путь)] += 1
        return
    fh = gzip.open(путь, 'rt', encoding='utf-8', errors='replace') if gz else io.open(путь, encoding='utf-8', errors='replace')
    with fh:
        for s in fh:
            s = s.strip()
            if s:
                try:
                    yield json.loads(s)
                except ValueError:
                    pass


def чист(s):
    s = re.sub(r'\s+', ' ', str(s if s is not None else '')).strip()
    return '' if s.lower() in ('none', 'null', 'nan') else s


ОПФ = (('ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ', 'ООО'), ('НЕПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'АО'),
       ('ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ПАО'), ('ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ЗАО'),
       ('ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО', 'ОАО'), ('АКЦИОНЕРНОЕ ОБЩЕСТВО', 'АО'),
       ('СЕЛЬСКОХОЗЯЙСТВЕННЫЙ ПРОИЗВОДСТВЕННЫЙ КООПЕРАТИВ', 'СПК'), ('ИНДИВИДУАЛЬНЫЙ ПРЕДПРИНИМАТЕЛЬ', 'ИП'))


def имя_чист(s):
    s = чист(html.unescape(чист(s))).replace('""', '"')
    if re.search(r'&\w*$', s) or not re.sub(r'\b(ООО|АО|ПАО|ЗАО|ОАО|ИП|СПК)\b|["«»\s]', '', s):
        return ''
    if s.count('"') % 2:
        s += '"'
    return s


def кратко_опф(s):
    s = чист(s)
    for а, б in ОПФ:
        s = re.sub(а, б, s, flags=re.I)
    return s


def число(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        т = str(v).lower().replace('\xa0', ' ').replace('руб.', '').replace('руб', '').strip()
        м = re.match(r'^(-?[\d ]+(?:[.,]\d+)?)\s*(трлн|млрд|млн|тыс)?', т)
        if not м:
            return None
        try:
            x = float(м.group(1).replace(' ', '').replace(',', '.'))
        except ValueError:
            return None
        x *= {'трлн': 1e12, 'млрд': 1e9, 'млн': 1e6, 'тыс': 1e3}.get(м.group(2), 1)
    return int(round(x)) if x else None


def год(v):
    м = re.search(r'(19|20)\d\d', str(v or ''))
    return м.group(0) if м else ''


КОД = re.compile(r'^\s*(\d{2}(?:\.\d{1,2}){0,2})\b\s*[-–—:]?\s*(.*)$')
СЛОВАРЬ = {}


def оквэд(s):
    м = КОД.match(чист(s))
    return (м.group(1), м.group(2).strip()) if м else ('', '')


def в_словарь(s):
    к, и = оквэд(s)
    if к and и and к not in СЛОВАРЬ:
        СЛОВАРЬ[к] = и


def регион_из_адреса(а):
    а = (а or '').lower()
    if re.search(r'кемеровская\s+обл|обл\w*\.?\s+кемеровская|кузбасс', а):
        return 'Кемеровская область - Кузбасс'
    if re.search(r'(?<!\w)томская\s+обл|обл\w*\.?\s+томская', а):
        return 'Томская область'
    if re.search(r'(?<!\w)омская\s+обл|обл\w*\.?\s+омская', а):
        return 'Омская область'
    return ''


def ограничить(s, n=300):
    s = чист(s)
    return s if len(s) <= n else s[:n - 3].rstrip(' ,;:') + '...'


def iso(d):
    if isinstance(d, (datetime.date, datetime.datetime)):
        return d.strftime('%Y-%m-%d')
    d = чист(d)
    м = re.match(r'^(\d{4})-(\d{2})-(\d{2})', d)
    if м:
        return м.group(0)
    м = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})', d)
    return '%s-%s-%s' % (м.group(3), м.group(2), м.group(1)) if м else ''


def руб(x):
    if x >= 1e9:
        return ('%.1f млрд руб.' % (x / 1e9)).replace('.', ',', 1)
    if x >= 1e6:
        return ('%.1f млн руб.' % (x / 1e6)).replace('.', ',', 1)
    return '%d тыс. руб.' % round(x / 1e3)


U = {}
for x in jl(os.path.join(HZ, 'hz-univers.jsonl')):
    if x.get('inn'):
        U[str(x['inn'])] = x
п('вселенная', len(U))

профиль = {}


def проф(inn, источник, файл, имя='', код='', код_имя='', статус='', регион='', адрес='', рук='', должн='', сайт='',
         выручка=None, выр_год='', ссылка=''):
    inn = re.sub(r'\D', '', str(inn or ''))
    if inn not in U:
        return
    к, и = оквэд(код)
    if not к and код:
        СТАТ['оквэд не код'][файл] += 1
    з = {'inn': inn, 'имя': имя_чист(имя), 'оквэд': к, 'оквэд_имя': чист(код_имя) or и, 'статус': чист(статус),
         'регион': чист(регион), 'адрес': чист(адрес), 'руководитель': чист(рук), 'должность': чист(должн),
         'сайт': чист(сайт), 'выручка': число(выручка), 'выручка_год': год(выр_год) if число(выручка) else '',
         'источник': источник, 'ссылка': чист(ссылка), 'источник_файл': файл}
    if not any(з[k] for k in ('имя', 'оквэд', 'статус', 'регион', 'адрес', 'руководитель', 'сайт')) and з['выручка'] is None:
        СТАТ['профиль пуст'][файл] += 1
        return
    ключ = (inn, источник)
    if ключ in профиль:
        старое = профиль[ключ]
        for k, v in з.items():
            if старое.get(k) in ('', None) and v not in ('', None):
                старое[k] = v
        if файл not in старое['источник_файл'].split('; '):
            старое['источник_файл'] += '; ' + файл
        return
    профиль[ключ] = з


# --- словарь ОКВЭД (код -> название) из уже собранных файлов
ob = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True)
for (s,) in ob.execute('select distinct okved_main from obzvon'):
    в_словарь(s)
park_okved = list(jl(os.path.join(D, 'PARK-OKVED-2S.jsonl')))
for x in park_okved:
    for s in x.get('okved_s_imenami') or []:
        в_словарь(s)
newsco = list(jl(os.path.join(D, 'newsco_targets.jsonl.gz'), gz=True))
for x in newsco:
    в_словарь(x.get('okved'))
п('словарь оквэд', len(СЛОВАРЬ))

# --- 1. база обзвона
ob.row_factory = sqlite3.Row
for r in ob.execute('select inn, name_short, name_full, okved_main, status, region, address, director, sites, revenue_rub, '
                    'revenue, god_otch from obzvon'):
    if r['inn'] in U:
        к, и = оквэд(r['okved_main'])
        проф(r['inn'], 'база обзвона (выгрузка)', 'obzvon-index.db', r['name_short'] or r['name_full'], к, и, r['status'],
             r['region'], r['address'], r['director'], '', r['sites'], r['revenue_rub'] or r['revenue'], r['god_otch'])
ob.close()
п('обзвон')

# --- 2. enrich.db
e = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True)
e.row_factory = sqlite3.Row
for r in e.execute('select inn, name, short_name, okved, region, site, revenue_rub, revenue_year, director, director_post, '
                   'status_egrul, address, istochnik_rekvizitov from companies'):
    if r['inn'] in U:
        проф(r['inn'], 'enrich.db (companies)', 'enrich.db: companies', r['short_name'] or r['name'], r['okved'], '',
             r['status_egrul'], r['region'], r['address'], r['director'], r['director_post'], r['site'], r['revenue_rub'],
             r['revenue_year'])
for r in e.execute('select inn, name_short, name_full, status, address, director, director_post, okved_main, okved_main_checko, '
                   'revenue_rub, fin_god, src, site_checko from requisites'):
    if r['inn'] in U:
        src = r['src'] or ''
        кто = 'checko' if 'checko' in src else 'DaData' if 'dadata' in src else (src or 'реквизиты')
        к1 = оквэд(r['okved_main'])[0]
        к2, и2 = оквэд(r['okved_main_checko'])
        к = к1 or к2
        проф(r['inn'], 'enrich.db (requisites, %s)' % кто, 'enrich.db: requisites', r['name_short'] or r['name_full'], к,
             и2 if к2 == к else '', DADATA_СТАТУС.get(r['status'] or '', r['status']), '', r['address'], r['director'],
             r['director_post'], r['site_checko'], r['revenue_rub'], r['fin_god'])
e.close()
п('enrich')

# --- 3. отборы КЦ / Meyer
for f, метка in (('kc1-spisok.json', 'отбор КЦ (kc1-spisok)'), ('meyer7-spisok.json', 'отбор Meyer (meyer7-spisok)')):
    o = json.load(io.open(os.path.join(S, f), encoding='utf-8'))
    for раздел in ('компании', 'на_решение'):
        for inn, x in (o.get(раздел) or {}).items():
            if inn not in U:
                continue
            откуда = чист(x.get('выручка_откуда'))
            проф(inn, метка + (', выручка: ' + откуда if откуда and число(x.get('выручка')) else ''), f, x.get('имя'), x.get('осн'), '', '',
                 x.get('регион'), '', '', '', x.get('сайт'), x.get('выручка'), откуда)
    СТАТ['отбор: пропущено «снято»'][f] = sum(1 for k in (o.get('снято') or {}) if k in U)
    del o
п('отборы')

# --- 4. DaData / checko
for x in jl(os.path.join(S, 'fsa-meyer-dadata.jsonl')):
    проф(x.get('инн'), 'DaData (ЕГРЮЛ)', 'fsa-meyer-dadata.jsonl', x.get('имя'), x.get('оквэд'), '',
         DADATA_СТАТУС.get(x.get('статус') or '', x.get('статус')), x.get('регион'), x.get('город'), x.get('руководитель'),
         x.get('должность'))
чк = {}
for f in ('fsa-meyer-checko.jsonl', os.path.join('hz', 'hz-checko.jsonl')):
    for x in jl(os.path.join(S, f)):
        if x.get('итог') == 'ok' and str(x.get('inn')) in U:
            чк[str(x['inn'])] = (x, os.path.basename(f))
for inn, (x, f) in чк.items():
    проф(inn, 'checko.ru (карточка)', f, '', x.get('оквэд'), '', x.get('статус'), x.get('регион'), '', x.get('руководитель'),
         x.get('должность'), '', x.get('выручка'), x.get('выручка_год'), x.get('ссылка'))
for x in park_okved:
    кк = x.get('okved_kody') or []
    им = x.get('okved_s_imenami') or []
    к = кк[0] if кк else ''
    и = next((оквэд(s)[1] for s in им if оквэд(s)[0] == к), '')
    проф(x.get('inn'), 'checko.ru (виды деятельности)', 'PARK-OKVED-2S.jsonl', x.get('predpriyatie'), к, и,
         ссылка=x.get('ssylka'))
for x in jl(os.path.join(D, 'PARK-CHECKO-2S.jsonl')):
    проф(x.get('inn'), 'checko.ru (PARK-CHECKO-2S)', 'PARK-CHECKO-2S.jsonl', x.get('predpriyatie'), x.get('okved'), '', '',
         '', '', '', '', x.get('sayt'), x.get('vyruchka'), x.get('vyruchka_god'), x.get('ssylka_kartochka') or x.get('kartochka'))
for x in jl(os.path.join(D, 'PARK-DADATA-2S.jsonl')):
    if x.get('error'):
        continue
    проф(x.get('inn'), 'DaData (ЕГРЮЛ), PARK-DADATA-2S', 'PARK-DADATA-2S.jsonl', x.get('name') or x.get('full_name'),
         x.get('okved'), '', DADATA_СТАТУС.get(x.get('status') or '', x.get('status')), '', x.get('address'), x.get('mgmt_name'),
         x.get('mgmt_post'), ссылка=x.get('ssylka'))
п('dadata/checko')

# --- 5. мастер-база, news-цели
m = sqlite3.connect(r'file:C:\sender\master-base.sqlite?mode=ro', uri=True)
m.row_factory = sqlite3.Row
for r in m.execute('select inn, name, name_obzvon, okved, region, address, egrul_status, director, revenue_rub, site from master'):
    if r['inn'] in U:
        к, и = оквэд(r['okved'])
        проф(r['inn'], 'мастер-база (master-base)', 'master-base.sqlite', r['name_obzvon'] or r['name'], к, и, r['egrul_status'],
             r['region'], r['address'], r['director'], '', r['site'], r['revenue_rub'])
m.close()
for x in newsco:
    к, и = оквэд(x.get('okved'))
    проф(x.get('inn'), 'цели news-скана (newsco_targets)', 'newsco_targets.jsonl.gz', x.get('krat') or x.get('poln'), к, и, '',
         x.get('region'), x.get('city'), сайт=x.get('site'), выручка=x.get('rev'))
del newsco, park_okved
п('мастер/newsco')

# --- 6. ФСА (заявитель), Цербер (имя и ОКВЭД ЕГРЮЛ)
фса_id = {}
for x in jl(os.path.join(S, 'fsa-meyer-kontakty2.jsonl')):
    i = str(x.get('инн') or '')
    if i in U and x.get('id') and i not in фса_id:
        фса_id[i] = x['id']
фса = []
for x in jl(os.path.join(S, 'fsa-meyer-izg.jsonl')):
    i = str(x.get('инн') or '')
    if i not in U:
        continue
    фса.append(x)
    проф(i, 'декларации ФСА (изготовитель)', 'fsa-meyer-izg.jsonl', x.get('имя'), '', '', '',
         регион_из_адреса(x.get('адрес')), x.get('адрес'), ссылка=(ФСА_URL % фса_id[i]) if i in фса_id else '')
ц2 = {}
for x in jl(os.path.join(S, 'cerber-meyer-inn2.jsonl')):
    if x.get('инн') and x.get('как') == 'Цербер подтвердил по ИНН':
        ц2[(x['юрлицо'], x['рег'])] = x
        проф(x['инн'], 'Цербер (сверка по ИНН)', 'cerber-meyer-inn2.jsonl', x.get('имя_егрюл'), x.get('оквэд'))
сверено = {y['инн'] for y in ц2.values()}
for x in jl(os.path.join(S, 'cerber-meyer-inn.jsonl')):
    if x.get('инн') and x['инн'] not in сверено:
        проф(x['инн'], 'Цербер (подбор по названию)', 'cerber-meyer-inn.jsonl', x.get('имя_егрюл'), x.get('оквэд'))
п('фса/цербер')

# --- 7. ФНС (доход 2025) — для каждого ИНН вселенной
for inn, x in U.items():
    v = число(x.get('доход_фнс_2025'))
    профиль[(inn, 'ФНС (доход 2025)')] = {
        'inn': inn, 'имя': '', 'оквэд': '', 'оквэд_имя': '', 'статус': '', 'регион': '', 'адрес': '', 'руководитель': '',
        'должность': '', 'сайт': '', 'выручка': v, 'выручка_год': '2025' if v else '', 'источник': 'ФНС (доход 2025)',
        'ссылка': ФНС_URL, 'источник_файл': 'hz-univers.jsonl (revexp.zip ФНС)'}
    if v is None:
        СТАТ['ФНС без дохода (во вселенной по выручке базы)']['hz-univers.jsonl'] += 1

for з in профиль.values():
    if з['оквэд'] and not з['оквэд_имя'] and з['оквэд'] in СЛОВАРЬ:
        з['оквэд_имя'] = СЛОВАРЬ[з['оквэд']]
        СТАТ['оквэд_имя из словаря'][з['источник_файл']] += 1

# ============ ФАКТЫ ============
факты = []
видел = set()


def факт(inn, тип, дата, описание, ссылка, номер, файл):
    inn = re.sub(r'\D', '', str(inn or ''))
    if inn not in U:
        return
    ключ = (inn, тип, номер or ссылка or описание)
    if ключ in видел:
        СТАТ['факт: дубль'][файл] += 1
        return
    видел.add(ключ)
    факты.append({'inn': inn, 'тип': тип, 'дата': iso(дата), 'описание': ограничить(описание), 'ссылка': чист(ссылка),
                  'номер': чист(номер), 'источник_файл': файл})
    СТАТ['факты'][тип] += 1


СЛОВО = {'Успешна': 'успешна', 'Провалена': 'провалена', 'В работе': 'активна'}


def напр_по_воронке(в):
    в = (в or '').strip()
    return 'СЦ' if в.startswith('СЦ') else 'Meyer' if 'MEYER' in в.upper() else 'КЦ'


# --- сделки: csv КЦ+СЦ (с номером)
fh = io.open(os.path.join(D, 'kc-sc-sdelki-0910.csv'), encoding='utf-8-sig')
г = fh.readline()
кол = next(csv.reader([г], delimiter=';'))
csv_по_инн = collections.defaultdict(list)
активные = set()
for r in csv.DictReader(fh, fieldnames=кол, delimiter=';'):
    i = re.sub(r'\D', '', r.get('INN') or '')
    if i in U:
        csv_по_инн[i].append(r)
fh.close()
for i, рр in csv_по_инн.items():
    for r in рр:
        ст = r['СТАТУС']
        закрыта = ст in ('Успешна', 'Провалена')
        if not закрыта:
            активные.add(i)
        оп = '%s, %s: сделка №%s «%s», воронка «%s», стадия «%s», создана %s%s' % (
            напр_по_воронке(r['ВОРОНКА']), СЛОВО.get(ст, ст.lower()), r['DEAL_ID'], ограничить(r['TITLE'], 110), r['ВОРОНКА'],
            r['СТАДИЯ'], r['DATE_CREATE'], (', закрыта ' + r['CLOSEDATE']) if закрыта and r['CLOSEDATE'] else '')
        факт(i, 'сделка', r['CLOSEDATE'] if закрыта and r['CLOSEDATE'] else r['DATE_CREATE'], оп, '', r['DEAL_ID'],
             'kc-sc-sdelki-0910.csv')

# --- активные Meyer (с номером)
ма = collections.defaultdict(list)
for r in csv.reader(io.open(os.path.join(D, 'meyer7-sdelki-aktivnye.tsv'), encoding='utf-8-sig'), delimiter='\t'):
    if len(r) < 2 or r[0] not in U or (len(r) > 2 and r[2] != 'ИНН'):
        continue
    for кус in r[1].split('; '):
        м = re.match(r'№(\d+)\s+(.*?)\s+/\s+(.*)$', кус.strip())
        if м:
            ма[r[0]].append((int(м.group(1)), м.group(2), м.group(3)))

# --- сводка по ИНН: то, чего нет в csv
vse = json.load(io.open(os.path.join(D, 'sdelki-vse-1410.json'), encoding='utf-8'))
for i in U:
    сд = vse.get(i) or []
    ост = list(csv_по_инн.get(i, []))
    мейер_в_работе = []
    сп = sorted(ма.get(i, []))
    for d in сд:
        напр, ст, d1, d2 = (list(d) + ['', '', '', ''])[:4]
        if напр in ('kc', 'sc'):
            пара = next((r for r in ост if r['СТАТУС'] == ст and r['DATE_CREATE'] == d1), None)
            if пара is not None:
                ост.remove(пара)
                СТАТ['факт: дубль']['sdelki-vse-1410.json'] += 1
                continue
        if напр == 'meyer' and ст == 'В работе' and len(мейер_в_работе) < len(сп):
            мейер_в_работе.append(d1)
            continue
        if ст == 'В работе':
            активные.add(i)
        закрыта = ст in ('Успешна', 'Провалена')
        оп = '%s, %s: сделка (Битрикс, номер в сводке не указан), создана %s%s' % (
            {'kc': 'КЦ', 'sc': 'СЦ', 'meyer': 'Meyer'}.get(напр, напр), СЛОВО.get(ст, ст.lower()), d1,
            (', закрыта ' + d2) if закрыта and d2 else '')
        факт(i, 'сделка', d2 if закрыта and d2 else d1, оп, '', '', 'sdelki-vse-1410.json')
    даты = sorted(мейер_в_работе) if len(мейер_в_работе) == len(сп) else []
    for k, (ид, вор, стадия) in enumerate(сп):
        активные.add(i)
        d1 = даты[k] if даты else ''
        оп = 'Meyer, активна: сделка №%s, воронка «%s», стадия «%s»%s' % (ид, вор, стадия, (', создана ' + d1) if d1 else '')
        факт(i, 'сделка', d1, оп, '', str(ид), 'meyer7-sdelki-aktivnye.tsv' + ('; sdelki-vse-1410.json' if d1 else ''))
del vse

# kc-sdelki-aktivnye.tsv и bitrix-kc.json: проверка покрытия csv (дубли не пишем)
ид_csv = {r['DEAL_ID'] for рр in csv_по_инн.values() for r in рр}
for r in csv.reader(io.open(os.path.join(D, 'kc-sdelki-aktivnye.tsv'), encoding='utf-8-sig'), delimiter='\t'):
    if len(r) >= 2 and r[0] in U:
        for кус in r[1].split('; '):
            м = re.match(r'№(\d+)\s+(.*?)\s+/\s+(.*)$', кус.strip())
            if not м:
                continue
            if м.group(1) in ид_csv:
                СТАТ['факт: дубль']['kc-sdelki-aktivnye.tsv'] += 1
            else:
                активные.add(r[0])
                факт(r[0], 'сделка', '', '%s, активна: сделка №%s, воронка «%s», стадия «%s»' % (
                    напр_по_воронке(м.group(2)), м.group(1), м.group(2), м.group(3)), '', м.group(1), 'kc-sdelki-aktivnye.tsv')
bk = json.load(io.open(os.path.join(D, 'bitrix-kc.json'), encoding='utf-8'))
for i, x in bk.items():
    if i not in U:
        continue
    if i in csv_по_инн:
        СТАТ['факт: дубль']['bitrix-kc.json'] += 1
        continue
    вор = ', '.join('%s: %s' % (k, v) for k, v in (x.get('voronki') or {}).items())
    факт(i, 'сделка', '', 'КЦ/СЦ: в Битриксе %s сделок%s' % (x.get('sdelok'), (' (воронки: %s)' % вор) if вор else ''), '', '',
         'bitrix-kc.json')
del bk

# --- стоп-лист панели
for x in json.load(io.open(os.path.join(D, 'sdelki-inn.json'), encoding='utf-8')):
    i = str(x.get('value') or '')
    if x.get('scope') != 'inn' or i not in U:
        continue
    причина, ист, d = x.get('reason') or '', чист(x.get('source')), (x.get('created_at') or '')[:10]
    if причина == 'competitor':
        факт(i, 'прочее', d, 'В стоп-листе панели рассыльщика как конкурент (%s)' % ист, '', '', 'sdelki-inn.json')
    elif i in активные:
        СТАТ['факт: дубль']['sdelki-inn.json'] += 1
    else:
        факт(i, 'сделка', d, 'Стоп-лист панели рассыльщика с %s: идёт сделка (%s, %s)' % (d, причина, ист), '', '',
             'sdelki-inn.json')
п('сделки')

# --- декларации ФСА
for x in фса:
    i = str(x['инн'])
    пр, уже = [], set()
    for s in x.get('продукция') or []:
        s = чист(s).strip(' .,;')
        if s and s.lower() not in уже:
            уже.add(s.lower())
            пр.append(s)
    n, сам = x.get('деклараций') or 0, x.get('сам_заявитель') or 0
    оп = 'Изготовитель в декларациях ЕАЭС (реестр ФСА): %s шт.%s, последняя %s; продукция: %s' % (
        n, (', в %s сам заявитель' % сам) if сам else '', x.get('последняя') or 'н/д', '; '.join(пр) or 'н/д')
    факт(i, 'декларация ФСА', x.get('последняя'), оп, (ФСА_URL % фса_id[i]) if i in фса_id else '', '',
         'fsa-meyer-izg.jsonl' + ('; fsa-meyer-kontakty2.jsonl' if i in фса_id else ''))


# --- Цербер
def рег_ц(а):
    м = re.search(r'Российская Федерация, ([^,]+)', а or '')
    return (м.group(1) if м else '').replace('обл.', '').replace('край', '').replace('Респ.', '').strip().lower()[:12]


цер = collections.OrderedDict()
for x in jl(os.path.join(S, 'cerber-meyer.jsonl')):
    if not x.get('номер'):
        continue
    y = ц2.get((x.get('юрлицо'), рег_ц(x.get('юр_адрес') or x.get('адрес'))))
    if not y:
        СТАТ['цербер: ИНН не подтверждён или вне вселенной']['cerber-meyer.jsonl'] += 1
        continue
    к = (y['инн'], x['номер'])
    if к not in цер:
        цер[к] = {'виды': [], 'x': x}
    if x.get('вид') and x['вид'] not in цер[к]['виды']:
        цер[к]['виды'].append(x['вид'])
for (i, ном), z in цер.items():
    x = z['x']
    оп = 'Аттестовано в реестре Цербер (Россельхознадзор): %s; объект «%s», %s%s' % (
        '; '.join(z['виды']) or 'вид не указан', кратко_опф(x.get('объект')), чист(x.get('адрес')),
        ('; продукция: ' + ', '.join(x['продукция'][:4])) if x.get('продукция') else '')
    факт(i, 'аттестация Цербер', '', оп, ЦЕРБЕР_URL, ном, 'cerber-meyer.jsonl; cerber-meyer-inn2.jsonl')
п('фса/цербер факты')

# --- паспорта производства
лучший = {}
for f in ('kc1-pasport.jsonl', 'meyer7-pasport.jsonl'):
    for x in jl(os.path.join(S, f)):
        i = str(x.get('inn') or '')
        p = x.get('паспорт')
        if i not in U or not isinstance(p, dict):
            continue
        if (p.get('уверенность') or '') == 'низкая':
            СТАТ['паспорт: низкая уверенность'][f] += 1
            continue
        части = []
        for k, подпись in (('мощности', 'мощности'), ('оборудование_линии', 'оборудование'), ('сырьё', 'сырьё'),
                           ('энергохозяйство', 'энергохозяйство'), ('масштаб', 'масштаб')):
            v = [чист(s) for s in (p.get(k) or []) if чист(s)]
            if v:
                части.append('%s: %s' % (подпись, '; '.join(v[:4])))
        if not части and p.get('продукция'):
            части.append('продукция: ' + '; '.join(чист(s) for s in p['продукция'][:6]))
        if not части:
            СТАТ['паспорт: пустой'][f] += 1
            continue
        ист = [u for u in (p.get('источники') or []) if str(u).startswith('http')]
        сайт = чист(x.get('сайт'))
        ссылка = ист[0] if ист else (сайт if сайт.startswith('http') else ('http://' + сайт if сайт else ''))
        оп = 'Сайт %s: %s' % (re.sub(r'^https?://(www\.)?', '', сайт).strip('/') or 'компании', ' | '.join(части))
        вес = len(' '.join(части))
        if i not in лучший or вес > лучший[i][0]:
            if i in лучший:
                СТАТ['факт: дубль']['паспорт (второй файл)'] += 1
            лучший[i] = (вес, оп, ссылка, f)
        else:
            СТАТ['факт: дубль']['паспорт (второй файл)'] += 1
for i, (вес, оп, ссылка, f) in лучший.items():
    факт(i, 'паспорт производства', '', оп, ссылка, '', f)
п('паспорта')

# --- книга продаж
import openpyxl  # noqa: E402
wb = openpyxl.load_workbook(os.path.join(D, 'Company.xlsx'), read_only=True, data_only=True)
ws = wb['Исходники']
кн = collections.defaultdict(list)
коды = collections.Counter()
for k, row in enumerate(ws.iter_rows(values_only=True)):
    if k == 0 or not row or len(row) < 5:
        continue
    i = re.sub(r'\D', '', str(row[2] or ''))
    коды[чист(row[0])] += 1
    if i in U and число(row[4]):
        кн[i].append((iso(row[1]), float(row[4]), чист(row[0])))
wb.close()
for i, сп in кн.items():
    сп.sort()
    сумма = sum(s for _, s, _ in сп)
    дд = [d for d, _, _ in сп if d]
    оп = 'Покупал у ООО «Руспром» (книга продаж): операций %s, на %s без НДС, с %s по %s' % (
        len(сп), руб(сумма), дд[0] if дд else 'н/д', дд[-1] if дд else 'н/д')
    факт(i, 'клиент (книга продаж)', дд[-1] if дд else '', оп, '', '', 'Company.xlsx (лист «Исходники»)')
СТАТ['книга продаж: коды операций'] = коды
п('книга продаж')


def записать(путь, строки):
    вр = путь + '.tmp'
    with io.open(вр, 'w', encoding='utf-8', newline='\n') as f:
        for з in строки:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(вр, путь)


пр = sorted(профиль.values(), key=lambda з: (з['inn'], з['источник']))
факты.sort(key=lambda з: (з['inn'], з['тип'], з['дата']))
записать(ПРОФ, пр)
записать(ФАКТ, факты)
print('===ИТОГ===')
print(json.dumps({
    'вселенная': len(U), 'сек': int(time.time() - t0),
    'профиль': {'записей': len(пр), 'ИНН': len({з['inn'] for з in пр}),
                'по источникам': collections.Counter(з['источник'] for з in пр),
                'с оквэд': sum(1 for з in пр if з['оквэд']), 'оквэд без имени': sum(1 for з in пр if з['оквэд'] and not з['оквэд_имя'])},
    'факты': {'записей': len(факты), 'ИНН': len({з['inn'] for з in факты}),
              'по типам': collections.Counter(з['тип'] for з in факты),
              'ИНН по типам': collections.Counter(t for t, _ in {(з['тип'], з['inn']) for з in факты}),
              'по файлам': collections.Counter(з['источник_файл'] for з in факты),
              'со ссылкой': sum(1 for з in факты if з['ссылка'])},
    'служебное': {k: dict(v) for k, v in СТАТ.items() if k != 'факты'},
}, ensure_ascii=False))
