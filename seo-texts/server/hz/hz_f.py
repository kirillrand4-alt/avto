# -*- coding: utf-8 -*-
# 19.10, владелец: база холодного прозвона (Кемеровская/Томская/Омская, доход 2025 от 100 млн). Этап 2, группа f — ЗАКУПКИ.
# Только уже собранное на дропе (C:\seostat\drop\drop-storage), только ИНН из hz\hz-univers.jsonl:
#   «закупка»: etpgpb-po-kompaniyam / etpgpb-po-slovam / etpgpb-loty-vse (ЭТП ГПБ), PARK-ETPGPB-KANDIDATY-3S, rts-tender-centro,
#     roseltorg-centro, roseltorg-po-kompaniyam, portal-postavshchikov-centro, tp-zakupki-po-vladelcam (Tender.pro, без «ЧУЖАЯ»
#     для inn), закупки[] из kc1-kontakty-slim / meyer7-kontakty-posl (карточки ЕИС, только инн_на_странице), закупочные строки
#     FAKTY-s-priznakom-musora (без мусора; ЭПБ — группа g; водоканалы/hh — не закупки);
#   «план закупки»: plany-zakupki-chistye (без brak) + планы из FAKTY (без «план не по нашему предмету»);
#   «раздел закупок на сайте»: tender-sites-results / tender-sites2-results (фильтр страниц «закупки/поставщикам», одна запись на сайт);
#   «прочее»: FAKTY «есть на площадке» без процедуры — только если других фактов этой площадки у ИНН нет.
# Дубли одной процедуры из разных файлов склеиваются по № ЕИС / № или id процедуры на площадке / URL.
# Телефоны контактных лиц из карточек закупок (kc1/meyer7 закупки[].люди, rts *_kontakt) -> hz-telefony-f.jsonl.
# Выход: C:\sender\server\hz\hz-fakty-f.jsonl, hz-telefony-f.jsonl (перезапись через .tmp + fsync).
import csv, html, io, json, os, re, collections
from urllib.parse import unquote, urlsplit
csv.field_size_limit(10 ** 9)
D = r'C:\seostat\drop\drop-storage'
HZ = r'C:\sender\server\hz'
ВЫХ_Ф = os.path.join(HZ, 'hz-fakty-f.jsonl')
ВЫХ_Т = os.path.join(HZ, 'hz-telefony-f.jsonl')
U = {json.loads(l)['inn'] for l in open(os.path.join(HZ, 'hz-univers.jsonl'), encoding='utf-8')}
СТАДИЯ = {'completed': 'завершена', 'commission': 'работа комиссии', 'accepting': 'приём заявок', 'canceled': 'отменена',
          'cancelled': 'отменена', 'archive': 'архив'}
ФАКТЫ = []
ИНДЕКС = {}
ТЕЛ = {}
СЧ = collections.Counter()


def R(f):
    return csv.DictReader(open(os.path.join(D, f), encoding='utf-8-sig', errors='replace', newline=''), delimiter=';')


def чист(s):
    return re.sub(r'\s+', ' ', html.unescape(html.unescape(s or ''))).strip()


def дата(s):
    s = (s or '').strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return '%s-%s-%s' % m.groups()
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', s)
    if m:
        return '%s-%s-%s' % (m.group(3), m.group(2), m.group(1))
    return ''


def дд(iso):
    return '%s.%s.%s' % (iso[8:10], iso[5:7], iso[:4]) if iso else ''


def сумма(s):
    m = re.match(r'\s*(\d[\d\s\xa0]*(?:[.,]\d{1,2})?)', s or '')
    if not m:
        return ''
    t = re.sub(r'[^\d,.]', '', m.group(1))
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    try:
        v = float(t)
    except ValueError:
        return ''
    if v <= 0:
        return ''
    return '{:,.0f} ₽'.format(v).replace(',', ' ')


def год_еис(n):
    return '20' + n[1:3] if re.fullmatch(r'3\d{10}', n or '') else ''


def ключ_номер(площадка, n):
    n = (n or '').strip()
    if not n:
        return None
    if re.fullmatch(r'3\d{10}|\d{19}', n):
        return ('еис', n)
    return (площадка, n)


def ключи_ссылки(u):
    u = (u or '').strip()
    if not u:
        return set()
    к = {('url', u.split('#')[0].rstrip('/').replace('http://', 'https://').replace('://www.', '://'))}
    m = re.search(r'etpgpb\.ru/procedures?/(?:tender/)?([a-z]+)/(\d+)', u)
    if m:
        к.add(('etp', m.group(1) + '/' + m.group(2)))
    m = re.search(r'roseltorg\.ru/procedure/([A-Z0-9]+)', u)
    if m:
        к.add(ключ_номер('Росэлторг', m.group(1)))
    m = re.search(r'rts-tender\.ru/poisk/id/l(3\d{10})-', u)
    if m:
        к.add(('еис', m.group(1)))
    m = re.search(r'tender\.pro/api/tender/(\d+)', u)
    if m:
        к.add(('Tender.pro', m.group(1)))
    m = re.search(r'regNumber=(\d+)', u)
    if m:
        к.add(ключ_номер('ЕИС', m.group(1)))
    m = re.search(r'zakupki\.mos\.ru/need/(\d+)', u)
    if m:
        к.add(('Портал поставщиков', m.group(1)))
    m = re.search(r'tektorg\.ru/market/procedures/(\d+)', u)
    if m:
        к.add(('ТЭК-Торг', m.group(1)))
    return к


def ключ_плана(u, текст):
    return ('план-текст', (u or '').split('&')[0], норм(текст))


def норм(s):
    return re.sub(r'[^0-9a-zа-яё]', '', (s or '').lower())[:90]


def добавить(инн, тип, файл, ключи, ссылка='', номер='', дата_='', площадка='', роль='', предмет='', сумма_='', способ='',
             стадия='', доп='', лот=False, дата_в_оп=True, тихо=False, только_индекс=()):
    ключи = {k for k in ключи if k}
    if re.fullmatch(r'[\d\s()№.,-]*(?:лот\s*№?\s*\d+)?[\s()]*', предмет or '', re.I):
        предмет = ''
    for k in ключи:
        e = ИНДЕКС.get((инн, k))
        if e is not None:
            break
    else:
        e = None
    if e is None:
        e = {'inn': инн, 'тип': тип, 'дата': дата_, 'площадка': площадка, 'роль': роль, 'предмет': предмет, 'лоты': [],
             'сумма': сумма_, 'способ': способ, 'стадия': стадия, 'доп': [доп] if доп else [], 'номер': номер, 'ссылка': ссылка,
             'файлы': [файл], 'ключи': set(), 'дата_в_оп': дата_в_оп}
        ФАКТЫ.append(e)
        СЧ['новый ' + файл] += 1
    else:
        СЧ['склеен ' + файл] += 1
        for п, з in (('дата', дата_), ('площадка', площадка), ('сумма', сумма_), ('способ', способ), ('стадия', стадия),
                     ('номер', номер), ('предмет', предмет)):
            if з and not e[п]:
                e[п] = з
        if тихо:
            номер = доп = предмет = ''
        if номер and re.fullmatch(r'3\d{10}', номер) and not re.fullmatch(r'3\d{10}', e['номер']):
            e['доп'].append('№ на площадке %s' % e['номер'])
            e['номер'] = номер
        elif номер and номер != e['номер'] and ('№ на площадке %s' % номер) not in e['доп']:
            e['доп'].append('№ на площадке %s' % номер)
        if роль and (not e['роль'] or '/' in e['роль']) and '/' not in роль:
            e['роль'] = роль
        if ссылка and (not e['ссылка'] or ('search=' in e['ссылка'] and 'search=' not in ссылка)):
            e['ссылка'] = ссылка
        if предмет and норм(предмет) != норм(e['предмет']) and норм(предмет) not in {норм(x) for x in e['лоты']}:
            if лот or норм(предмет)[:40] not in норм(e['предмет']):
                e['лоты'].append(предмет)
        if доп and доп not in e['доп']:
            e['доп'].append(доп)
        if файл not in e['файлы']:
            e['файлы'].append(файл)
    for k in ключи | set(только_индекс):
        ИНДЕКС[(инн, k)] = e
        e['ключи'].add(k)
    return e


def описание(e):
    ч = []
    if e['дата'] and e['дата_в_оп']:
        ч.append(дд(e['дата']))
    шапка = e['площадка'] or ''
    if e['роль']:
        шапка += (', ' if шапка else '') + e['роль']
    if шапка:
        ч.append(шапка + ':')
    if e['предмет']:
        ч.append('«%s»' % e['предмет'][:170])
    хвост = []
    if e['лоты']:
        хвост.append('лоты: ' + '; '.join(x[:80] for x in e['лоты'][:4]) + (' и ещё %d' % (len(e['лоты']) - 4) if len(e['лоты']) > 4 else ''))
    for п in ('сумма', 'способ', 'стадия'):
        if e[п]:
            хвост.append(e[п])
    хвост += e['доп']
    s = ' '.join(ч)
    if хвост:
        s += ', ' + ', '.join(хвост)
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= 300 else s[:297].rstrip(' ,;') + '…'


def тел(сырой):
    s = сырой or ''
    доб = ''
    m = re.search(r'(?:доб|вн|ext)\.?\s*(\d{1,6})', s, re.I)
    if m:
        доб = m.group(1)
        s = s[:m.start()]
    d = re.sub(r'\D', '', s)
    if len(d) == 10 and d[0] in '3489':
        d = '7' + d
    if len(d) > 11 and d[0] in '78' and not доб and len(d) <= 16:
        доб, d = d[11:], d[:11]
    if len(d) != 11 or d[0] not in '78' or d[1] not in '3489':
        return None
    return '+7' + d[1:], доб


def телефон(инн, сырой, фио, должн, роль, источник, ссылка, цитата, файл):
    for кусок in re.split(r'[;,]', сырой or ''):
        t = тел(кусок)
        if not t:
            continue
        k = (инн, t[0], t[1], фио)
        if k in ТЕЛ:
            continue
        ТЕЛ[k] = {'inn': инн, 'телефон': t[0], 'доб': t[1], 'фио': фио, 'должность': должн, 'роль': роль,
                  'источник': источник, 'ссылка': ссылка, 'цитата': цитата[:300], 'источник_файл': файл}


def этп_гпб():
    ф = 'etpgpb-po-kompaniyam.csv'
    for r in R(ф):
        i = r['inn'].strip()
        if i not in U:
            continue
        продажа = r['vid'].strip() == 'продажа'
        д = дата(r['data'])
        добавить(i, 'прочее' if продажа else 'закупка', ф, {ключ_номер('ЭТП ГПБ', r['nomer'])} | ключи_ссылки(r['ssylka']),
                 ссылка=r['ssylka'].strip(), номер=r['nomer'].strip(), дата_=д,
                 площадка='ЭТП ГПБ (%s)' % r['sekciya'].strip() if r['sekciya'].strip() else 'ЭТП ГПБ',
                 роль='продавец, торги на продажу' if продажа else 'организатор/заказчик', предмет=чист(r['predmet']),
                 сумма_=сумма(r['summa']), стадия=СТАДИЯ.get(r['stadiya'].strip(), r['stadiya'].strip()),
                 доп='' if д else ('год по № ЕИС %s' % год_еис(r['nomer']) if год_еис(r['nomer']) else ''))
    ф = 'etpgpb-po-slovam.csv'
    for r in R(ф):
        i = r['inn'].strip()
        if i not in U:
            continue
        добавить(i, 'закупка', ф, {ключ_номер('ЭТП ГПБ', r['nomer'])} | ключи_ссылки(r['ssylka']), ссылка=r['ssylka'].strip(),
                 номер=r['nomer'].strip(), дата_=дата(r['data']),
                 площадка='ЭТП ГПБ (%s)' % r['sekciya'].strip() if r['sekciya'].strip() else 'ЭТП ГПБ', роль='заказчик',
                 предмет=чист(r['predmet']), сумма_=сумма(r['summa']))
    ф = 'etpgpb-loty-vse.csv'
    for r in R(ф):
        орг = set(re.findall(r'\d{10,12}', r['inn_organizatora']))
        зак = set(re.findall(r'\d{10,12}', r['inn_zakazchikov']))
        for i in (орг | зак) & U:
            if i in орг and i in зак:
                роль = 'заказчик и организатор'
            elif i in зак:
                роль = 'заказчик' + (' (организатор %s)' % чист(r['organizator'])[:40] if орг and чист(r['organizator']) else '')
            else:
                роль = 'организатор для %s' % (чист(r['zakazchiki'])[:50] or 'другого заказчика')
            добавить(i, 'закупка', ф, {ключ_номер('ЭТП ГПБ', r['reestrovyy_nomer'])} | ключи_ссылки(r['ssylka']),
                     ссылка=r['ssylka'].strip(), номер=r['reestrovyy_nomer'].strip(), дата_=дата(r['data_publikacii']),
                     площадка='ЭТП ГПБ (%s)' % r['sekciya'].strip() if r['sekciya'].strip() else 'ЭТП ГПБ', роль=роль,
                     предмет=чист(r['predmet']), сумма_=сумма(r['summa']), способ=чист(r['tip_procedury']).lower(),
                     стадия=СТАДИЯ.get(r['stadiya'].strip(), r['stadiya'].strip()), лот=True)
    ф = 'PARK-ETPGPB-KANDIDATY-3S.jsonl'
    по_тексту = collections.defaultdict(list)
    for e in ФАКТЫ:
        if e['площадка'].startswith('ЭТП ГПБ'):
            по_тексту[(e['inn'], норм(e['предмет']))].append(e)
    for l in open(os.path.join(D, ф), encoding='utf-8'):
        x = json.loads(l)
        i = str(x.get('inn') or '').strip()
        if i not in U:
            continue
        к = {('ЭТП ГПБ', x['nomer'])}
        совп = по_тексту.get((i, норм(x.get('nazvanie'))), [])
        if len(совп) == 1:
            к |= {next(iter(совп[0]['ключи']))}
        вид = (x.get('vid') or '').strip()
        добавить(i, 'закупка', ф, к, ссылка=x.get('ssylka') or '', номер=x['nomer'], площадка='ЭТП ГПБ',
                 роль='организатор/заказчик', предмет=чист(x.get('nazvanie')),
                 доп=('компрессорный парк: %s%s' % (вид, ', ЗИП/услуги' if x.get('zip_ili_uslugi') else '')) if вид else '')


def площадки():
    ф = 'rts-tender-centro.csv'
    for r in R(ф):
        for i in {r['zakazchik_inn'].strip(), r['organizator_inn'].strip()} & U:
            if i == r['zakazchik_inn'].strip():
                роль = 'заказчик'
            else:
                роль = 'организатор для %s' % чист(r['zakazchik'])[:50]
            д, до = дата(r['data_publikacii']), дата(r['data_okonchaniya'])
            добавить(i, 'закупка', ф, {ключ_номер('РТС-тендер', r['nomer'])} | ключи_ссылки(r['ssylka']), ссылка=r['ssylka'].strip(),
                     номер=r['nomer'].strip(), дата_=д, площадка='РТС-тендер (%s)' % r['zakon'].strip() if r['zakon'].strip() else 'РТС-тендер',
                     роль=роль, предмет=чист(r['predmet']), сумма_=сумма(r['cena']), доп='приём заявок до %s' % дд(до) if до else '')
            for кол, кто in (('zakazchik_kontakt', 'заказчика'), ('organizator_kontakt', 'организатора')):
                if r[кол].strip() and r[кол.replace('kontakt', 'inn')].strip() == i:
                    телефон(i, r[кол].split(';')[0], '', '', 'контакт %s по закупке' % кто, 'РТС-тендер (карточка закупки)',
                            r['ssylka'].strip(), '%s; закупка № %s «%s»' % (чист(r[кол]), r['nomer'].strip(), чист(r['predmet'])[:120]), ф)
    ф = 'roseltorg-centro.csv'
    for r in R(ф):
        for i in {r['zakazchik_inn'].strip(), r['organizator_inn'].strip()} & U:
            роль = 'заказчик' if i == r['zakazchik_inn'].strip() else 'организатор' + (' для %s' % чист(r['zakazchik'])[:50] if чист(r['zakazchik']) else '')
            до = дата(r['data_okonchaniya'])
            добавить(i, 'закупка', ф, {ключ_номер('Росэлторг', r['nomer'])} | ключи_ссылки(r['ssylka']), ссылка=r['ssylka'].strip(),
                     номер=r['nomer'].strip(), дата_=до,
                     площадка='Росэлторг (%s)' % r['sekciya'].strip() if r['sekciya'].strip() else 'Росэлторг', роль=роль,
                     предмет=чист(r['predmet']), сумма_=сумма(r['cena']), стадия=чист(r['status']).lower(),
                     доп='приём заявок до %s' % дд(до) if до else '', дата_в_оп=False)
    ф = 'roseltorg-po-kompaniyam.csv'
    for r in R(ф):
        i = r['inn'].strip()
        if i not in U:
            continue
        д = дата(r['data'])
        добавить(i, 'закупка', ф, {ключ_номер('Росэлторг', r['nomer'])} | ключи_ссылки(r['ssylka']), ссылка=r['ssylka'].strip(),
                 номер=r['nomer'].strip(), дата_=д, площадка='Росэлторг', роль='заказчик' if чист(r['zakazchik']) else 'организатор/заказчик',
                 предмет=чист(r['predmet']), сумма_=сумма(r['summa']), стадия=чист(r['stadiya']).lower(),
                 доп='' if д else ('год по № ЕИС %s' % год_еис(r['nomer']) if год_еис(r['nomer']) else ''))
    ф = 'portal-postavshchikov-centro.csv'
    for r in R(ф):
        for i in {r['zakazchik_inn'].strip(), r['organizator_inn'].strip()} & U:
            роль = 'заказчик' if i == r['zakazchik_inn'].strip() else 'организатор для %s' % чист(r['zakazchik'])[:50]
            д, до = дата(r['data_nachala']), дата(r['data_okonchaniya'])
            добавить(i, 'закупка', ф, {ключ_номер('Портал поставщиков', r['nomer'])} | ключи_ссылки(r['ssylka']),
                     ссылка=r['ssylka'].strip(), номер=r['nomer'].strip(), дата_=д,
                     площадка='Портал поставщиков (zakupki.mos.ru%s)' % (', ' + r['tip'].strip() if r['tip'].strip() else ''),
                     роль=роль, предмет=чист(r['predmet']), сумма_=сумма(r['cena']), стадия=чист(r['status']).lower(),
                     доп='приём до %s' % дд(до) if до else '')
    ф = 'tp-zakupki-po-vladelcam.csv'
    for r in R(ф):
        чья = r['chya_zakupka'].strip()
        кому = set()
        if r['inn_vladelca'].strip() in U:
            кому.add(r['inn_vladelca'].strip())
        if r['inn'].strip() in U and 'ЧУЖАЯ' not in чья:
            кому.add(r['inn'].strip())
        for i in кому:
            if i == r['inn_vladelca'].strip():
                роль = 'заказчик (%s)' % чист(r['company'])[:60]
            else:
                роль = 'закупка филиала/дочки: %s, ИНН %s' % (чист(r['vladelec_nazvanie'] or r['company'])[:50], r['inn_vladelca'].strip())
            u = 'https://www.tender.pro/api/tender/%s/view_public' % r['tender_id'].strip() if r['tender_id'].strip() else ''
            добавить(i, 'закупка', ф, {('Tender.pro', r['tender_id'].strip())} | ключи_ссылки(u), ссылка=u,
                     номер=r['tender_id'].strip(), дата_=дата(r['sozdan']), площадка='Tender.pro', роль=роль,
                     предмет=чист(r['predmet']), доп='приём до %s' % чист(r['do']) if чист(r['do']) else '')


def еис_из_обхода():
    for ф in ('kc1-kontakty-slim.jsonl', 'meyer7-kontakty-posl.jsonl'):
        for l in open(os.path.join(D, ф), encoding='utf-8', errors='replace'):
            i = l[9:21].split('"')[0]
            if i not in U:
                continue
            o = json.loads(l)
            if str(o.get('inn')) != i:
                continue
            for q in o.get('закупки') or []:
                u = (q.get('url') or '').strip()
                if not u:
                    continue
                if not q.get('инн_на_странице'):
                    СЧ['ЕИС-обход: ИНН не на странице, пропуск'] += 1
                    continue
                т = чист(q.get('предмет'))
                m = re.search(r'regNumber=(\d+)', u)
                н = m.group(1) if m else ''
                пред = re.split(r'\s(?:Заказчик|Организация, осуществляющая размещение)\s', т)[0]
                роль = 'заказчик' if ' Заказчик ' in т else ('организатор' if 'осуществляющая размещение' in т else 'заказчик/организатор')
                ц = re.search(r'Начальная цена\s*(\d[\d\s]*,\d{2})', т)
                р = re.search(r'Размещено\s*(\d{2}\.\d{2}\.\d{4})', т)
                ок = re.search(r'Окончание подачи заявок\s*(\d{2}\.\d{2}\.\d{4})', т)
                добавить(i, 'закупка', ф, {ключ_номер('ЕИС', н)} | ключи_ссылки(u), ссылка=u, номер=н,
                         дата_=дата(р.group(1)) if р else '', площадка='ЕИС (223-ФЗ)' if '/223/' in u else 'ЕИС', роль=роль,
                         предмет=пред, сумма_=сумма(ц.group(1)) if ц else '',
                         доп='окончание подачи заявок %s' % ок.group(1) if ок else '')
                for ч in q.get('люди') or []:
                    телефон(i, str(ч.get('phone') or ''), чист(ч.get('person')), чист(ч.get('post')), 'контактное лицо по закупке',
                            'ЕИС (карточка закупки)', u,
                            'Контактное лицо: %s%s; закупка № %s «%s»' % (чист(ч.get('person')),
                                                                           ', ' + ч['email'] if ч.get('email') else '', н, пред[:120]), ф)


ИСТ_ФАКТЫ = {'ЭТП ГПБ': 'ЭТП ГПБ', 'Tender.pro': 'Tender.pro', 'Росэлторг': 'Росэлторг', 'Сбербанк-АСТ': 'Сбербанк-АСТ',
             'РТС-тендер': 'РТС-тендер', 'Портал поставщиков Москвы': 'Портал поставщиков (zakupki.mos.ru)',
             'ТЭК-Торг': 'ТЭК-Торг', 'план закупки 223-ФЗ, ЕИС': 'план закупки ЕИС (223-ФЗ)'}
СОСТ = {'покупает': 'заказчик', 'есть на площадке': 'заказчик/организатор', 'планировал': 'заказчик', 'есть': 'заказчик'}


def факты_файл():
    ф = 'FAKTY-s-priznakom-musora.csv'
    только_площадка = []
    for r in R(ф):
        i = r['inn'].strip()
        if i not in U:
            continue
        if r['musor'].strip():
            СЧ['FAKTY мусор, пропуск'] += 1
            continue
        ист = r['istochnik'].strip()
        if ист not in ИСТ_ФАКТЫ:
            СЧ['FAKTY не закупка (%s), пропуск' % ист[:25]] += 1
            continue
        if r['sostoyanie'].strip() == 'план не по нашему предмету':
            СЧ['FAKTY план не по нашему предмету, пропуск'] += 1
            continue
        u = r['ssylka'].strip()
        т = чист(r['tekst'])
        if not u and (not т or re.fullmatch(r'[\d.]+', т)):
            только_площадка.append((i, ист, т))
            continue
        план = ист.startswith('план закупки')
        д = дата(r['data'])
        мес = '' if д else (r['data'].strip() if re.fullmatch(r'\d{2}\.\d{4}', r['data'].strip()) else '')
        добавить(i, 'план закупки' if план else 'закупка', ф, {ключ_плана(u, т)} if план else ключи_ссылки(u), ссылка=u, дата_=д,
                 площадка=ИСТ_ФАКТЫ[ист],
                 роль=СОСТ.get(r['sostoyanie'].strip(), ''), предмет=т,
                 доп=('план. размещение %s' % мес) if мес else '', тихо=True)
    for i, ист, т in только_площадка:
        пл = ИСТ_ФАКТЫ[ист]
        if any(e['inn'] == i and e['площадка'].startswith(пл.split(' (')[0]) for e in ФАКТЫ):
            СЧ['FAKTY «есть на площадке» при наличии процедур, пропуск'] += 1
            continue
        e = добавить(i, 'прочее', ф, {('площадка', пл)}, площадка=пл)
        e['текст'] = 'есть в выгрузке площадки %s (организация на площадке), конкретная процедура в выгрузке не указана' % пл


def планы():
    ф = 'plany-zakupki-chistye.csv'
    строки = [r for r in R(ф) if r['inn'].strip() in U]
    строки.sort(key=lambda r: дата(r['data_razmeshcheniya']), reverse=True)
    for r in строки:
        i = r['inn'].strip()
        if r['brak'].strip():
            СЧ['plany brak, пропуск'] += 1
            continue
        пред = чист(r['predmet_bez_proekta'] or r['predmet'])
        доп = []
        if r['planiruemaya_data_razmeshcheniya'].strip():
            доп.append('план. размещение %s' % r['planiruemaya_data_razmeshcheniya'].strip())
        if r['srok_ispolneniya_dogovora'].strip():
            доп.append('исполнение до %s' % r['srok_ispolneniya_dogovora'].strip())
        if r['okpd2'].strip():
            доп.append('ОКПД2 %s' % r['okpd2'].strip())
        н = '%s поз. %s' % (r['plan_reg_nomer'].strip(), r['nomer_pozicii'].strip()) if r['plan_reg_nomer'].strip() else ''
        тк = {ключ_плана(r['ssylka'], r['predmet']), ключ_плана(r['ssylka'], r['predmet_bez_proekta'])}
        сп = чист(r['sposob_zakupki'])
        добавить(i, 'план закупки', ф, {('план', н)} if н else тк, только_индекс=тк, ссылка=r['ssylka'].strip(),
                 номер=н, дата_=дата(r['data_razmeshcheniya']), площадка='план закупки ЕИС (223-ФЗ)', роль='заказчик',
                 предмет=пред, сумма_=сумма(r['summa']), способ=('способ: ' + сп) if сп else '', доп=', '.join(доп), тихо=True)


ДА = re.compile(r'закуп|тендер|tender|zakup|purchas|поставщик|postav|supplier|снабжени|потребност', re.I)
НЕТ = re.compile(r'конкурс|konkurs|теплоснаб|водоснаб|vodosnab|teplosnab|heat-supply|ипотек|mortgage|покупк|дистриб|distrib|'
                 r'выбор|vybor|день поставщика|omskportal|zakupki\.gov|zakup-metall|zakup-lom|закуп металла|закуп\w* лом|'
                 r'лома\b|оптов|krupniy-opt|nashikh-postavshchikov|наших поставщиков', re.I)
САЙТ_ЧУЖОЙ = {('4240009967', 'pkspskov.ru'), ('4220025150', 'vdk.ru')}
МЕТКИ = {'gpb': 'ЭТП ГПБ', 'rts': 'РТС-тендер', 'eis': 'ЕИС', 'sber': 'Сбербанк-АСТ', 'roseltorg': 'Росэлторг',
         'tektorg': 'ТЭК-Торг', 'b2b': 'B2B-Center', 'fabrikant': 'Фабрикант', 'tenderpro': 'Tender.pro'}


def имя_раздела(u, a, т):
    путь = unquote(urlsplit(u).path)
    if a and not a.startswith('path:') and len(a) < 8 and т and ДА.search(т) and len(т) <= 30:
        и = т
    elif a and not a.startswith('path:') and (ДА.search(a) or len(a) >= 8):
        и = a
    elif т and ДА.search(т):
        и = т
    else:
        и = '' if a.startswith('path:') else a
    if not и:
        return 'по адресу %s' % путь
    return и if ДА.search(и) else '%s (%s)' % (и, путь)


def сайты():
    for ф in ('tender-sites-results.json', 'tender-sites2-results.json'):
        for x in json.load(open(os.path.join(D, ф), encoding='utf-8')):
            i = str(x.get('inn') or '').strip()
            if i not in U:
                continue
            стр = {p['url'].rstrip('/'): p for p in x.get('pages') or [] if p.get('url')}
            канд = [(u, a) for u, a in x.get('links') or []] + [(p['url'], p.get('anchor') or '') for p in x.get('pages') or []]
            по_хосту = collections.OrderedDict()
            for u, a in канд:
                k = u.rstrip('/')
                p = стр.get(k, {})
                if p.get('status') not in (None, 200):
                    continue
                т = чист(p.get('title'))
                a = чист(a)
                s = ' '.join([unquote(u), a, т])
                if not ДА.search(s) or НЕТ.search(s):
                    continue
                if re.search(r'/news|novost|novosti', u, re.I) and not re.search(r'закуп|тендер', a + ' ' + т, re.I):
                    continue
                if re.match(r'\d{1,2}\.\d{2}\.\d{4}', a):
                    continue
                h = urlsplit(u).netloc.lower().replace('www.', '')
                if (i, h) in САЙТ_ЧУЖОЙ:
                    СЧ['сайт другой организации, пропуск'] += 1
                    continue
                г = по_хосту.setdefault(h, {'стр': collections.OrderedDict(), 'метки': set(), 'лоты': 0})
                if k not in г['стр']:
                    г['стр'][k] = (u, имя_раздела(u, a, т))
                for m in (p.get('marks') or {}):
                    г['метки'].add(МЕТКИ.get(m, m))
                г['лоты'] = max(г['лоты'], int(p.get('lots') or 0))
            for h, г in по_хосту.items():
                ссылки = sorted(г['стр'].values(), key=lambda z: len(z[0]))
                u0, a0 = ссылки[0]
                назв = list(dict.fromkeys(a for _, a in ссылки if a))
                try:
                    хост = h.encode().decode('idna') if 'xn--' in h else h
                except UnicodeError:
                    хост = h
                н0 = (назв[0] if назв else 'по адресу ' + unquote(urlsplit(u0).path))[:80]
                пред = 'на сайте %s есть раздел %s' % (хост, н0 if н0.startswith('по адресу') else '«%s»' % н0)
                доп = []
                if len(назв) > 1:
                    доп.append('подразделы: ' + '; '.join(назв[1:])[:120])
                if г['метки']:
                    доп.append('на странице ссылки на площадки: ' + ', '.join(sorted(г['метки'])))
                if г['лоты']:
                    доп.append('лотов на странице: %d' % г['лоты'])
                e = добавить(i, 'раздел закупок на сайте', ф, {('сайт', h)}, ссылка=u0, площадка='', роль='', предмет='',
                             доп='')
                e['текст'] = пред + ('' if not доп else ', ' + ', '.join(доп))


def записать(путь, строки):
    tmp = путь + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        for x in строки:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, путь)


def main():
    этп_гпб()
    площадки()
    еис_из_обхода()
    планы()
    факты_файл()
    сайты()
    вых = []
    for e in ФАКТЫ:
        оп = e.get('текст') or описание(e)
        вых.append({'inn': e['inn'], 'тип': e['тип'], 'дата': e['дата'], 'описание': оп[:300], 'ссылка': e['ссылка'],
                    'номер': e['номер'], 'источник_файл': '; '.join(e['файлы'])})
    вых.sort(key=lambda z: (z['inn'], z['тип'], z['дата']), reverse=False)
    записать(ВЫХ_Ф, вых)
    записать(ВЫХ_Т, list(ТЕЛ.values()))
    по_типу = collections.Counter(z['тип'] for z in вых)
    инн_типа = collections.defaultdict(set)
    for z in вых:
        инн_типа[z['тип']].add(z['inn'])
    по_файлу = collections.Counter()
    инн_файла = collections.defaultdict(set)
    for z in вых:
        for ф in z['источник_файл'].split('; '):
            по_файлу[ф] += 1
            инн_файла[ф].add(z['inn'])
    print('===ИТОГ===')
    видел = collections.Counter()
    for z in вых:
        к = z['источник_файл'].split('; ')[0]
        if видел[к] < 1:
            видел[к] += 1
            print('·', json.dumps(z, ensure_ascii=False)[:330])
    for t in list(ТЕЛ.values())[:2]:
        print('☎', json.dumps(t, ensure_ascii=False)[:300])
    print(json.dumps({'факты': len(вых), 'инн': len({z['inn'] for z in вых}), 'без_ссылки': sum(1 for z in вых if not z['ссылка']),
                      'телефоны': len(ТЕЛ), 'инн_тел': len({t['inn'] for t in ТЕЛ.values()})}, ensure_ascii=False))
    print('ТИП', {k: (v, len(инн_типа[k])) for k, v in по_типу.items()})
    print('ФАЙЛ', {k: (v, len(инн_файла[k])) for k, v in по_файлу.most_common()})
    print('СЧ', dict(СЧ))


if __name__ == '__main__':
    main()
