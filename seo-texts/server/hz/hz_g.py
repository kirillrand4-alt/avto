# -*- coding: utf-8 -*-
# 19.10, база холодного прозвона (Кемеровская/Томская/Омская, доход 2025 от 100 млн), этап 2, буква g: ПРОМБЕЗОПАСНОСТЬ,
# ОБОРУДОВАНИЕ, СОБЫТИЯ. Только уже собранное: дроп C:\seostat\drop\drop-storage\ (чтение), строки с ИНН из вселенной
# C:\sender\server\hz\hz-univers.jsonl. Выход: C:\sender\server\hz\hz-fakty-g.jsonl (формат брифа этапа 2).
#   ЭПБ: park-snimok.db (fakt + fakt_ssylka monitor-pb), PARK-FAKTY-2S-EPB(-POLNYE), PARK-VYDACHA-FAKTY-2S, VAZHNOE-3s-EPB-*,
#        PARK-SROK-EPB-2S, epb-*.csv, EPB-OKNO-ZAMENY, DOLIVKA-EPB, PARK-EPB-PROVERENO, FAKTY-s-priznakom-musora (ЭПБ без
#        мусора), mpb-po-inn; дубли схлопнуты по № заключения.
#   ОПО: PARK-VYDACHA-OPO-2S, PARK-OPO-PO-INN-2S, sbor-opo(-2), opo-po-inn.
#   ЕГРЗ: PROIZVODSTVA-/PORTFEL-RAZOBRANO, EGRZ-NASHA-TEMA-2, egrz_90d_1709, EGRZ-*.xlsx, KOMPRESSORNYE-STANCII-EGRZ.xlsx
#         (ключ — ИНН застройщика; «отсеяно» не берём).
#   событие: signaly-*-1709, sobytiya-1709, vygruzka-sobytiy.json, 3s_proekt_uliki (+3s_proekty), SIPR-ZAYAVITELI-INN.
#   патент: VAZHNOE-3s-PATENTY (без «слабого запроса»). оборудование: park-snimok.db (не ЭПБ), atlas_copco.db/fakty.
# Стоп-лист фактов: OTSEV-*, OTZYV-*, VAZHNOE-3s-MUSOR-*, VAZHNOE-3s-SVERNUTO-*, мусор FAKTY-s-priznakom-musora. Не стопим
# причины, которые говорят лишь «не центробежная / не воздух / поршневая-винтовая / газ» — для обзвона это всё равно машина.
import collections, csv, io, json, os, re, sqlite3, sys, time, urllib.parse
csv.field_size_limit(10 ** 9)
D = r'C:\seostat\drop\drop-storage'
HZ = r'C:\sender\server\hz'
ВЫХ = os.path.join(HZ, 'hz-fakty-g.jsonl')
СТАТ = collections.Counter()
СТОП_ПРИЧИНЫ = collections.Counter()
НЕ_СТОП = re.compile(r'центробежн\w* не назван|поршнев|винтов|роторн|вихрев|тип не установлен|^наша машина|нашего производства|'
                     r'текста нет|среда|газов|non_air', re.I)
ЛАТ = str.maketrans('ABCEHKMOPTXY', 'АВСЕНКМОРТХУ')


def читать_вселенную():
    у = set()
    for s in io.open(os.path.join(HZ, 'hz-univers.jsonl'), encoding='utf-8'):
        try:
            у.add(json.loads(s)['inn'])
        except (ValueError, KeyError):
            pass
    return у


У = читать_вселенную()


def строки(имя):
    п = os.path.join(D, имя)
    if not os.path.exists(п):
        СТАТ['нет файла ' + имя] += 1
        return
    if имя.endswith('.jsonl'):
        for l in io.open(п, encoding='utf-8-sig', errors='replace'):
            l = l.strip()
            if l:
                try:
                    r = json.loads(l)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    yield r
        return
    f = io.open(п, encoding='utf-8-sig', errors='replace', newline='')
    первая = f.readline()
    f.seek(0)
    дл = max([';', ',', '\t'], key=lambda c: первая.count(c))
    for r in csv.DictReader(f, delimiter=дл):
        yield {(k or '').lstrip('\ufeff').replace('п»ї', ''): (v or '') for k, v in r.items()}


def xlsx_строки(имя, пропуск=r'Отсеян'):
    import openpyxl
    п = os.path.join(D, имя)
    if not os.path.exists(п):
        СТАТ['нет файла ' + имя] += 1
        return
    wb = openpyxl.load_workbook(п, read_only=True)
    for ws in wb.worksheets:
        if re.search(пропуск, ws.title, re.I):
            continue
        it = ws.iter_rows(values_only=True)
        hd = [str(x) if x is not None else '' for x in (next(it, None) or ())]
        if 'ИНН застройщика' not in hd:
            continue
        for r in it:
            yield ws.title, {k: ('' if v is None else str(v)) for k, v in zip(hd, r)}


def инн(v):
    v = re.sub(r'\D', '', str(v or ''))
    return v if v in У else ''


def чисто(s, n=None):
    s = re.sub(r'\s+', ' ', str(s or '').replace('&quot;', '"').replace('&amp;', '&')).strip()
    s = s.replace('—', '-').replace('–', '-')
    return s[:n] if n else s


def обрез(s, n=300):
    s = чисто(s)
    if len(s) <= n:
        return s
    return s[:n - 1].rsplit(' ', 1)[0].rstrip(' ,;:') + '…'


МЕС = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}


def дата(s):
    s = str(s or '').strip()
    м = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if м:
        return '%s-%s-%s' % м.groups()
    м = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', s)
    if м:
        return '%s-%02d-%02d' % (м.group(3), int(м.group(2)), int(м.group(1)))
    м = re.search(r'(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})', s)
    if м:
        return '%s-%02d-%02d' % (м.group(3), МЕС[м.group(2)], int(м.group(1)))
    return ''


def норм_url(u):
    u = urllib.parse.unquote(чисто(u)).lower()
    u = re.sub(r'^https?://(www\.)?', '', u).rstrip('/')
    return u


def норм_текст(s, n=50):
    return re.sub(r'[^0-9a-zа-яё]', '', чисто(s).lower())[:n]


НОМЕР_ЭПБ = re.compile(r'(\d{2,3}-[A-ZА-ЯЁ]{1,3}-\d{3,7}-\d{4})')


def номер_эпб(*поля):
    for s in поля:
        s = urllib.parse.unquote(str(s or ''))
        м = НОМЕР_ЭПБ.search(s.upper().translate(ЛАТ))
        if м:
            return м.group(1)
    return ''


def ссылка_эпб(*поля):
    for s in поля:
        s = чисто(s)
        if 'monitor-pb.ru/conclusion/' in s:
            return re.search(r'https?://\S+', s).group(0) if re.search(r'https?://\S+', s) else s
    return ''


def url_из(*поля):
    for s in поля:
        м = re.search(r'https?://[^\s|;,]+', str(s or ''))
        if м:
            return м.group(0)
    return ''


# ---------- стоп-лист ----------
СТОП_URL = {}
СТОП_ТЕКСТ = {}


def в_стоп(i, url, текст, причина, файл):
    if not i:
        return
    if НЕ_СТОП.search(причина or ''):
        СТАТ['стоп: не стопим (тип/среда) ' + файл] += 1
        return
    if url:
        СТОП_URL.setdefault((i, норм_url(url)), []).append((норм_текст(текст, 40), '%s: %s' % (файл, чисто(причина, 60))))
    elif len(норм_текст(текст, 400)) >= 120:
        СТОП_ТЕКСТ[(i, норм_текст(текст, 200))] = '%s: %s' % (файл, чисто(причина, 60))


def собрать_стоп():
    for r in строки('OTSEV-EPB-1-sessiya.csv'):
        в_стоп(инн(r.get('inn')), '', r.get('obekt'), r.get('prichina_otseva'), 'OTSEV-EPB-1-sessiya.csv')
    for r in строки('OTSEV-tip-mashiny.csv'):
        в_стоп(инн(r.get('inn')), r.get('ssylka'), r.get('tekst'), r.get('tip_mashiny'), 'OTSEV-tip-mashiny.csv')
    for имя, причина in (('OTZYV-2s-MUSORNYE-FAKTY-VSE.csv', ''), ('OTZYV-2s-FAKT-BEZ-MASHINY.csv', 'в тексте нет слова машины'),
                         ('OTZYV-2s-SADOVYE-VOZDUHODUVKI.csv', 'садовая воздуходувка'), ('OTZYV-2s-NEPROIZVODSTVO.csv', 'не производство'),
                         ('OTZYV-2s-CHUZHAYA-SREDA-fakty.csv', 'чужая среда')):
        for r in строки(имя):
            в_стоп(инн(r.get('inn')), r.get('ssylka') or r.get('ssylka_na_istochnik'), r.get('tekst') or r.get('predmet') or r.get('citata'),
                   причина or r.get('klass'), имя)
    по_id = {}
    for r in строки('DLYA-2S-FACT-ID-PO-SSYLKE.csv'):
        if инн(r.get('inn')):
            по_id[r.get('fact_id')] = r.get('ssylka')
    for r in строки('VAZHNOE-3s-MUSOR-FAKTOV-razmetka.csv'):
        i = инн(r.get('inn'))
        if i:
            в_стоп(i, по_id.get(r.get('id'), ''), r.get('citata'), r.get('musor_vid'), 'VAZHNOE-3s-MUSOR-FAKTOV-razmetka.csv')
    for r in строки('VAZHNOE-3s-SVERNUTO-musor.csv'):
        в_стоп(инн(r.get('inn')), по_id.get(r.get('value'), ''), r.get('citata'), r.get('vid'), 'VAZHNOE-3s-SVERNUTO-musor.csv')
    хорошие = set()
    мусор = []
    for r in строки('FAKTY-s-priznakom-musora.csv'):
        i = инн(r.get('inn'))
        if not i:
            continue
        if r.get('musor'):
            мусор.append((i, r.get('ssylka'), r.get('tekst'), 'мусор: ' + (r.get('prichina_musora') or '')))
        else:
            хорошие.add((i, норм_url(r.get('ssylka'))))
    for i, u, т, п in мусор:
        if (i, норм_url(u)) not in хорошие:
            в_стоп(i, u, т, п, 'FAKTY-s-priznakom-musora.csv')


def стоп(i, url, текст):
    for u in ([url] if isinstance(url, str) else url):
        if not u:
            continue
        зап = СТОП_URL.get((i, норм_url(u)))
        if зап:
            целая = 'monitor-pb.ru/conclusion/' in u
            т = норм_текст(текст, 40)
            for тт, причина in зап:
                if целая or not тт or not т or тт == т or тт in норм_текст(текст, 400):
                    return причина
    return None


# ---------- ЭПБ ----------
ЭПБ = {}


def эпб_добавить(i, файл, номер='', url='', дт='', объект='', машина='', вывод='', срок='', статус='', эо='', текст=''):
    номер = номер_эпб(номер, url, текст, объект)
    url_ок = ссылка_эпб(url)
    if not номер and not url_ок:
        СТАТ['ЭПБ без номера и ссылки: ' + файл] += 1
        return
    к = (i, номер or норм_url(url_ок))
    з = ЭПБ.setdefault(к, {'inn': i, 'номер': номер, 'url': '', 'дата': '', 'объект': '', 'машины': [], 'вывод': '', 'срок': '',
                           'статус': '', 'эо': '', 'текст': '', 'файлы': [], 'урлы': set()})
    if url_ок:
        з['урлы'].add(url_ок)
        if not з['url']:
            з['url'] = url_ок
    з['дата'] = з['дата'] or дата(дт)
    if объект and len(чисто(объект)) > len(з['объект']):
        з['объект'] = чисто(объект, 400)
    if текст and len(чисто(текст)) > len(з['текст']):
        з['текст'] = чисто(текст, 400)
    м = чисто(машина, 80)
    if м and м not in з['машины']:
        з['машины'].append(м)
    for п, v in (('вывод', вывод), ('срок', срок), ('статус', статус), ('эо', эо)):
        v = чисто(v, 80)
        if v and not з[п]:
            з[п] = v
    if файл not in з['файлы']:
        з['файлы'].append(файл)
    СТАТ['ЭПБ строк: ' + файл] += 1


def машина_из(*части):
    return ' '.join(чисто(x) for x in части if чисто(x) and чисто(x).lower() not in ('none', 'any'))


def эпб_файлы():
    for имя in ('PARK-FAKTY-2S-EPB-POLNYE.csv', 'PARK-FAKTY-2S-EPB.csv', 'PARK-VYDACHA-FAKTY-2S.csv'):
        for r in строки(имя):
            i = инн(r.get('inn'))
            if not i or 'monitor-pb' not in (r.get('ssylka') or '') + (r.get('istochnik') or ''):
                continue
            ист = r.get('istochnik') or ''
            эпб_добавить(i, имя, r.get('nomer_zaklucheniya'), r.get('ssylka') or ист, r.get('data'), '',
                         машина_из(r.get('tip'), r.get('marka_model'), ('зав.№ ' + r['zavodskoy_nomer']) if r.get('zavodskoy_nomer') else ''),
                         r.get('vyvod'), r.get('srok_do'), r.get('status_sroka'), ист if ист and not re.search(r'monitor|реестр|http', ист) else '',
                         r.get('citata'))
    for имя in ('VAZHNOE-3s-EPB-NASHI-MASHINY.csv', 'VAZHNOE-3s-EPB-HIMPROM-so-srokami.csv', 'EPB-OKNO-ZAMENY.csv',
                'VAZHNOE-3s-EPB-SROKI-CENTROBEZHNYE.csv', 'VAZHNOE-3s-EPB-SROKI-VOZDUSHNYE.csv'):
        for r in строки(имя):
            i = инн(r.get('inn'))
            if i:
                эпб_добавить(i, имя, r.get('nomer'), r.get('ssylka'), r.get('data'), r.get('obekt'), машина_из(r.get('marki')),
                             r.get('vyvod'), r.get('deystvuet_do'), r.get('status'), r.get('ekspertnaya_org'))
    for имя in sorted(n for n in os.listdir(D) if re.match(r'epb-(vozdushnye|atlas|copco|kopko|slitno)', n) and n.endswith('.csv')):
        for r in строки(имя):
            i = инн(r.get('inn_zakazchika'))
            if i:
                эпб_добавить(i, имя, r.get('nomer'), r.get('istochnik'), r.get('data'), r.get('obekt'), '', r.get('vyvod'), '',
                             {'active': 'действует', 'expired': 'истёк', 'expiring': 'истекает'}.get(r.get('srok'), ''), r.get('ekspertnaya_org'))
    for r in строки('PARK-SROK-EPB-2S.jsonl'):
        i = инн(r.get('inn'))
        if i:
            эпб_добавить(i, 'PARK-SROK-EPB-2S.jsonl', r.get('nomer'), r.get('ssylka'), '', '', '', '', r.get('srok_do'), r.get('status'), '',
                         r.get('citata'))
    for r in строки('DOLIVKA-EPB-v-panel-ot-1-sessii.csv'):
        i = инн(r.get('inn'))
        if i:
            ч = r.get('chem_dokazano') or ''
            м = re.search(r'вывод:\s*([^,;]+)', ч)
            эпб_добавить(i, 'DOLIVKA-EPB-v-panel-ot-1-sessii.csv', ч, r.get('ssylka'), r.get('data'), '',
                         машина_из(r.get('tip_mashiny'), r.get('marka')), м.group(1) if м else '', '', '', '', r.get('tekst'))
    for r in строки('PARK-EPB-PROVERENO-IZ-PESOCHNICY-3S.jsonl'):
        i = инн(r.get('inn'))
        if i:
            эпб_добавить(i, 'PARK-EPB-PROVERENO-IZ-PESOCHNICY-3S.jsonl', '', r.get('ssylka'), '', '', машина_из(r.get('vid')), '', '', '', '',
                         r.get('citata_mashiny'))
    for r in строки('FAKTY-s-priznakom-musora.csv'):
        i = инн(r.get('inn'))
        if i and 'ЭПБ' in (r.get('istochnik') or '') and not r.get('musor'):
            эпб_добавить(i, 'FAKTY-s-priznakom-musora.csv', '', r.get('ssylka'), r.get('data'), '', '', '', '', '', '', r.get('tekst'))
    for r in строки('mpb-po-inn.jsonl'):
        i = инн(r.get('inn'))
        for с in (r.get('stroki') or []) if i else []:
            if isinstance(с, dict):
                эпб_добавить(i, 'mpb-po-inn.jsonl', с.get('nomer'), с.get('ssylka'), с.get('data'), с.get('obekt'), '', с.get('vyvod'),
                             с.get('deystvuet_do') or с.get('srok'), '', с.get('ekspertnaya_org'))


# ---------- park-snimok.db ----------
ОБОР = {}
СОСТ = {'эксплуатирует': 'эксплуатирует', 'закупка': 'закупка', 'сервис': 'сервис/ремонт', 'покупает машину': 'покупает',
        'покупает ГАЗ': 'покупает газ', 'планирует': 'планирует закупку', 'арендует': 'арендует', 'продаёт (дилер)': 'продаёт (дилер)',
        'узел': 'узел/запчасти', 'неясно': 'упоминание'}


def вес_ссылки(u):
    u = u or ''
    if 'monitor-pb.ru/conclusion/' in u:
        return 0
    if 'zakupki.gov.ru' in u and re.search(r'regNumber=|/notice/|purchase|orderplan', u):
        return 1
    if re.search(r'etpgpb|tender\.pro|roseltorg|tektorg|rts-tender|sberbank-ast|zakupki\.mos', u):
        return 2
    if 'zakupki.gov.ru' in u:
        return 5
    if 'news.google' in u:
        return 4
    return 3


def номер_закупки(url, dedup=''):
    м = re.search(r'regNumber=(\d{11,19})', url or '')
    if м:
        return м.group(1)
    м = re.search(r'tender\.pro/(?:api/)?tender/(\d+)', url or '')
    if м:
        return 'tender.pro ' + м.group(1)
    м = re.search(r'\|(\d{11}|\d{19})$', dedup or '')
    if м:
        return м.group(1)
    м = re.search(r'id(\d{6,8})\)', dedup or '')
    return 'tender.pro ' + м.group(1) if м else ''


def обор_добавить(i, файл, url, номер, дт, описание, текст):
    к = (i, номер or норм_url(url) or норм_текст(описание, 80))
    з = ОБОР.get(к)
    if з is None or (len(описание) > len(з['описание']) and вес_ссылки(url) <= вес_ссылки(з['ссылка'])):
        ОБОР[к] = {'inn': i, 'тип': 'оборудование', 'дата': дата(дт), 'описание': описание, 'ссылка': url, 'номер': номер,
                   'источник_файл': файл, '_текст': текст}
        СТАТ['оборудование строк: ' + файл] += 1
    else:
        СТАТ['оборудование дубль: ' + файл] += 1


def снимок():
    db = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'park-snimok.db'), uri=True)
    db.execute('create temp table u(inn text primary key)')
    db.executemany('insert or ignore into temp.u values(?)', [(x,) for x in У])
    сс = collections.defaultdict(list)
    for fid, url, ист, нег in db.execute('select s.fakt_id, s.url, s.istochnik, s.negodnaya from fakt_ssylka s join fakt f on f.id=s.fakt_id '
                                         'where f.inn in (select inn from temp.u)'):
        if url and not (нег or '').strip():
            сс[fid].append((url, ист or ''))
    кол = ['id', 'inn', 'tip', 'sostoyanie', 'marka', 'model', 'napisanie', 'zavodskoy_nomer', 'sreda', 'summa', 'data_fakta', 'srok_do',
           'chto_naydeno', 'pochemu', 'karantin', 'vid_fakta', 'v_parke', 'dedup']
    for row in db.execute('select %s from fakt where inn in (select inn from temp.u)' % ','.join(кол)):
        f = dict(zip(кол, row))
        i = f['inn']
        if (f['karantin'] or '').strip() or f['vid_fakta'] == 'НЕТ' or f['tip'] == 'НЕ НАША МАШИНА' or not f['v_parke']:
            СТАТ['снимок: пропуск (карантин/не машина)'] += 1
            continue
        ссылки = sorted(сс.get(f['id'], []), key=lambda x: вес_ссылки(x[0]))
        if not ссылки:
            СТАТ['снимок: нет годной ссылки'] += 1
            continue
        марка = машина_из(f['marka'] if (f['marka'] or '').lower() not in (f['model'] or '').lower() else '', f['model'])
        маш = машина_из(f['tip'], марка, ('зав.№ ' + f['zavodskoy_nomer']) if f['zavodskoy_nomer'] else '')
        эпб = [u for u, _ in ссылки if 'monitor-pb.ru/conclusion/' in u]
        if эпб:
            м = re.search(r'вывод:\s*([^,;|]+)', f['pochemu'] or '')
            эпб_добавить(i, 'park-snimok.db', f['pochemu'], эпб[0], f['data_fakta'], '', маш, м.group(1) if м else '', f['srok_do'], '', '',
                         f['chto_naydeno'])
            continue
        url, ист = ссылки[0]
        текст = чисто(f['chto_naydeno'])
        текст = re.sub(r'\s+(машина|компрессора)$', '', текст)
        сумма = чисто(f['summa'])
        if re.match(r'^\d+(\.\d+)?$', сумма):
            сумма = '{:,.0f} руб.'.format(float(сумма)).replace(',', ' ')
        оп = '%s: %s; «%s»%s%s%s' % (СОСТ.get(f['sostoyanie'], f['sostoyanie'] or 'упоминание'), маш or f['tip'], обрез(текст, 170),
                                     ('; сумма ' + сумма) if сумма else '', ('; ' + ист) if ист else '',
                                     ('; ' + f['data_fakta']) if f['data_fakta'] and not дата(f['data_fakta']) else '')
        причина = стоп(i, [u for u, _ in ссылки], текст)
        if причина:
            СТОП_ПРИЧИНЫ['оборудование ' + причина] += 1
            continue
        обор_добавить(i, 'park-snimok.db', url, номер_закупки(url, f['dedup']), f['data_fakta'], обрез(оп), текст)


def атлас():
    db = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'atlas_copco.db'), uri=True)
    кол = ['inn', 'tip_fakta', 'chto_naydeno', 'model', 'napisanie', 'istochnik', 'ssylka', 'data_fakta', 'summa', 'dedup']
    ТИП = {'stoit': 'стоит на предприятии', 'pokupaet': 'покупает', 'prodaet': 'продаёт (дилер)', 'neyasno': 'упоминание'}
    for row in db.execute('select %s from fakty' % ','.join(кол)):
        f = dict(zip(кол, row))
        i = инн(f['inn'])
        if not i:
            continue
        текст = re.sub(r'\s+(машина|компрессора)$', '', чисто(f['chto_naydeno']))
        причина = стоп(i, f['ssylka'] or '', текст)
        if причина:
            СТОП_ПРИЧИНЫ['оборудование ' + причина] += 1
            continue
        url = чисто(f['ssylka'])
        оп = 'Atlas Copco%s, %s: «%s»%s' % ((' ' + чисто(f['model'])) if f['model'] else '', ТИП.get(f['tip_fakta'], f['tip_fakta']),
                                           обрез(текст, 200), ('; сумма ' + чисто(f['summa'])) if f['summa'] else '')
        if 'monitor-pb.ru/conclusion/' in url:
            эпб_добавить(i, 'atlas_copco.db', '', url, f['data_fakta'], '', 'Atlas Copco ' + чисто(f['model']), '', '', '', '', текст)
            continue
        обор_добавить(i, 'atlas_copco.db', url, номер_закупки(url, f['dedup']), f['data_fakta'], обрез(оп), текст)


def эпб_выдать():
    out = []
    for з in ЭПБ.values():
        причина = стоп(з['inn'], sorted(з['урлы']), з['объект'] or з['текст'])
        if not причина and з['объект']:
            причина = СТОП_ТЕКСТ.get((з['inn'], норм_текст(з['объект'], 200)))
        if причина:
            СТОП_ПРИЧИНЫ['ЭПБ ' + причина] += 1
            continue
        url = з['url'] or ('https://monitor-pb.ru/conclusion/' + urllib.parse.quote(з['номер']) if НОМЕР_ЭПБ.fullmatch(з['номер'] or '') else '')
        объект = з['объект'] or з['текст']
        объект = re.sub(r'^Заключение экспертизы промышленной безопасности\s*(No|№)?\s*', '', объект, flags=re.I)
        части = ['ЭПБ%s%s' % ((' № ' + з['номер']) if з['номер'] else '', (' от ' + '.'.join(reversed(з['дата'].split('-')))) if з['дата'] else '')]
        if объект:
            части[0] += ': ' + обрез(объект, 150)
        if з['машины']:
            части.append(обрез(', '.join(з['машины'][:3]), 80))
        if з['вывод']:
            части.append('вывод: ' + з['вывод'])
        if з['срок']:
            части.append('действует до ' + з['срок'])
        elif з['статус']:
            части.append('срок: ' + з['статус'])
        if з['эо']:
            части.append('эксперт: ' + з['эо'])
        out.append({'inn': з['inn'], 'тип': 'ЭПБ', 'дата': з['дата'], 'описание': обрез('; '.join(части)), 'ссылка': url,
                    'номер': з['номер'], 'источник_файл': з['файлы'][0]})
        СТАТ['ЭПБ слито из файлов: %d' % len(з['файлы'])] += 1
    return out


# ---------- ОПО ----------
def опо():
    out = {}

    def доб(i, файл, имя_оп, класс, рег, url, цит, дт):
        имя_оп = чисто(имя_оп).strip('«»" ')
        if not i or not имя_оп:
            return
        рег = чисто(рег)
        if not рег:
            м = re.search(r'(А\d{2}-\d{5}-\d{4})', чисто(имя_оп) + ' ' + чисто(цит))
            рег = м.group(1) if м else ''
        к = (i, рег or норм_текст(имя_оп, 60))
        оп = 'ОПО «%s»%s%s%s%s' % (обрез(имя_оп, 120), (', %s класс опасности' % класс) if чисто(класс) else '', (', рег.№ ' + рег) if рег else '',
                                   '; назван в заключении ЭПБ' if 'monitor-pb' in (url or '') else '', (': «%s»' % обрез(цит, 110)) if чисто(цит) else '')
        стар = out.get(к)
        if стар is None or (not стар['ссылка'] and url) or (len(оп) > len(стар['описание']) and url):
            out[к] = {'inn': i, 'тип': 'ОПО', 'дата': дата(дт), 'описание': обрез(оп), 'ссылка': чисто(url), 'номер': рег, 'источник_файл': файл}
        СТАТ['ОПО строк: ' + файл] += 1

    for r in строки('PARK-VYDACHA-OPO-2S.csv'):
        доб(инн(r.get('inn')), 'PARK-VYDACHA-OPO-2S.csv', r.get('naimenovanie_obekta'), r.get('klass_opasnosti'), r.get('reg_nomer'), r.get('ssylka'),
            r.get('citata'), '')
    for r in строки('PARK-OPO-PO-INN-2S.jsonl'):
        доб(инн(r.get('inn')), 'PARK-OPO-PO-INN-2S.jsonl', r.get('naimenovanie_obekta'), r.get('klass_opasnosti'), r.get('reg_nomer_opo'),
            r.get('ssylka'), r.get('citata'), r.get('data'))
    for имя in ('sbor-opo.jsonl', 'sbor-opo-2.jsonl', 'opo-po-inn.jsonl'):
        for r in строки(имя):
            i = инн(r.get('inn'))
            for о in (r.get('obekty') or []) if i else []:
                if isinstance(о, dict):
                    доб(i, имя, о.get('naimenovanie_obekta'), о.get('klass_opasnosti'), о.get('reg_nomer') or о.get('reg_nomer_opo'), о.get('ssylka'),
                        о.get('citata'), о.get('data'))
    return list(out.values())


# ---------- ЕГРЗ ----------
def егрз():
    out = {}

    def доб(i, файл, номер, url, дт, объект, вывод, вид, проект, квт=''):
        if not i:
            return
        номер = чисто(номер)
        if not номер:
            м = re.search(r'(\d{2}-\d-\d-\d-\d{6}-\d{4})', объект or '')
            номер = м.group(1) if м else ''
        объект = re.sub(r'\.?\s*Заключение \d{2}-\d-\d-\d-\d{6}-\d{4} от \d{4}-\d{2}-\d{2}\.?', '.', чисто(объект)).strip(' .')
        к = (i, номер or норм_url(url))
        if not к[1]:
            return
        оп = 'Госэкспертиза (ЕГРЗ)%s%s%s: «%s»' % ((': ' + чисто(вывод).lower()) if вывод else '', (' № ' + номер) if номер else '',
                                                  (' от ' + '.'.join(reversed(дата(дт).split('-')))) if дата(дт) else '', обрез(объект, 170))
        if чисто(вид):
            оп += '; ' + чисто(вид, 60)
        if чисто(проект) and чисто(проект).lower() != 'none':
            оп += '; проектировщик ' + обрез(проект, 70)
        if чисто(квт) and чисто(квт).lower() != 'none':
            оп += '; оценка компрессора ~%s кВт' % чисто(квт)
        стар = out.get(к)
        if стар is None or (len(оп) > len(стар['описание']) and (url or not стар['ссылка'])):
            out[к] = {'inn': i, 'тип': 'ЕГРЗ (госэкспертиза)', 'дата': дата(дт), 'описание': обрез(оп), 'ссылка': чисто(url), 'номер': номер,
                      'источник_файл': файл}
        СТАТ['ЕГРЗ строк: ' + файл] += 1

    for имя in ('PROIZVODSTVA-RAZOBRANO.jsonl', 'PORTFEL-RAZOBRANO.jsonl', 'EGRZ-NASHA-TEMA-2.jsonl'):
        for r in строки(имя):
            if str(r.get('klass') or '').startswith('отсеяно'):
                СТАТ['ЕГРЗ отсеяно: ' + имя] += 1
                continue
            доб(инн(r.get('zastroyshchik_inn')), имя, r.get('nomer_zaklyucheniya'), r.get('ssylka'), r.get('data'), r.get('obekt'), r.get('vyvod'),
                r.get('vid_dokumenta') if 'Проектная документация' not in (r.get('vid_dokumenta') or '') else '', r.get('proektirovshchik'))
    for r in строки('egrz_90d_1709.csv'):
        доб(инн(r.get('ИНН')), 'egrz_90d_1709.csv', '', r.get('ссылка'), r.get('дата_заключения'), r.get('объект'), '', r.get('вид_работ'), '')
    for имя in ('KOMPRESSORNYE-STANCII-EGRZ.xlsx', 'EGRZ-PROIZVODSTVA.xlsx', 'EGRZ-NASHA-TEMA.xlsx', 'EGRZ-NASHA-TEMA-TOLKO.xlsx',
                'EGRZ-OT-90-KVT-2025.xlsx', 'EGRZ-PORTFELI-LIC.xlsx'):
        for лист, r in xlsx_строки(имя):
            if str(r.get('Класс') or '').startswith('отсеяно'):
                continue
            вд = r.get('Вид документа') or ''
            доб(инн(r.get('ИНН застройщика')), имя, r.get('Номер заключения'), r.get('Ссылка на карточку') or r.get('Ссылка'), r.get('Дата заключения'),
                r.get('Объект'), r.get('Вывод экспертизы'), вд if вд and 'Проектная документация' not in вд else '', r.get('Проектировщик'),
                r.get('Оценка, кВт') if 'KVT' in имя else '')
    return list(out.values())


# ---------- события ----------
def события():
    out = {}
    инд = {}

    def доб(i, файл, тип, что, сумма, стадия, url, дт, увер=''):
        if not i or not чисто(что):
            return
        url = чисто(url)
        оп = '%s: %s' % (чисто(тип) or 'событие', обрез(что, 200))
        if чисто(сумма) and чисто(сумма).lower() != 'none' and норм_текст(сумма, 20) not in норм_текст(что, 300):
            оп += '; сумма ' + обрез(сумма, 60)
        if чисто(стадия):
            оп += '; стадия: ' + re.sub(r'^\d+\.?\s*', '', чисто(стадия))
        if увер == 'low':
            оп += ' [привязка к ИНН неуверенная]'
        ключи = ([(i, 'u', норм_url(url))] if url else []) + [(i, 'т', норм_текст(что, 60))]
        к = next((инд[x] for x in ключи if x in инд), ключи[0])
        for x in ключи:
            инд.setdefault(x, к)
        стар = out.get(к)
        нов = {'inn': i, 'тип': 'событие', 'дата': дата(дт), 'описание': обрез(оп), 'ссылка': url, 'номер': '', 'источник_файл': файл}
        if стар is None:
            out[к] = нов
        else:
            СТАТ['событие дубль: ' + файл] += 1
            лучше = (not стар['ссылка'] and url) or ('news.google' in стар['ссылка'] and url and 'news.google' not in url) or \
                    (len(нов['описание']) > len(стар['описание']) + 20 and bool(url) >= bool(стар['ссылка']))
            if лучше:
                нов['дата'] = нов['дата'] or стар['дата']
                out[к] = нов
            elif not стар['дата'] and нов['дата']:
                стар['дата'] = нов['дата']
        СТАТ['событие строк: ' + файл] += 1

    for имя in ('signaly-vse-1709.csv', 'signaly-chistye-1709.csv', 'signaly-novye-1709.csv', 'sobytiya-1709.csv'):
        for r in строки(имя):
            доб(инн(r.get('ИНН')), имя, r.get('тип события'), r.get('что происходит'), r.get('сумма'), r.get('стадия'), r.get('ссылка'),
                r.get('дата события'), r.get('уверенность в ИНН'))
    вг = json.load(io.open(os.path.join(D, 'vygruzka-sobytiy.json'), encoding='utf-8'))
    for x in вг.get('события') or []:
        if x.get('suspect') in (1, '1', True):
            СТАТ['событие suspect: vygruzka'] += 1
            continue
        доб(инн(x.get('inn')), 'vygruzka-sobytiy.json', x.get('event_type'), x.get('what'), x.get('sum'), x.get('стадия'), x.get('source_url'),
            x.get('ts'), x.get('inn_conf'))
    пр = {r.get('proekt_id'): r for r in строки('3s_proekty.csv')}
    for r in строки('3s_proekt_uliki.csv'):
        if (r.get('suspect') or '').strip() not in ('', '0', 'False'):
            continue
        п = пр.get(r.get('proekt_id')) or {}
        что = чисто(r.get('citata'))
        if п.get('obekt') and норм_текст(п['obekt'], 30) not in норм_текст(что, 300):
            что = '%s (объект: %s)' % (что, чисто(п['obekt'], 120))
        доб(инн(r.get('inn')), '3s_proekt_uliki.csv', r.get('event_type'), что, r.get('sum') or п.get('summa_rub'), r.get('stadiya'),
            r.get('source_url'), r.get('data_sobytiya') or r.get('ts'), r.get('inn_conf'))
    for r in строки('SIPR-ZAYAVITELI-INN.csv'):
        i = инн(r.get('inn'))
        if not i or (r.get('zayavitel_somnitelen') or '').strip() not in ('', '0', 'нет', 'False'):
            continue
        что = 'заявитель в %s: проект «%s», прирост %s МВт%s, %s кВ, год ввода %s, центр питания %s; документ %s, стр. %s' % (
            чисто(r.get('istochnik')) or 'СиПР', чисто(r.get('proekt')), чисто(r.get('uvelichenie_MVt_chislo')),
            (' (было %s)' % чисто(r.get('ranee_MVt_chislo'))) if чисто(r.get('ranee_MVt_chislo')) else '', чисто(r.get('napryazhenie_kV')),
            чисто(r.get('god_vvoda_syroj') or r.get('god_chislo')), чисто(r.get('centr_pitaniya'), 70), чисто(r.get('fajl')), чисто(r.get('stranica')))
        к = (i, 'sipr', чисто(r.get('fajl')), чисто(r.get('stranica')), чисто(r.get('nomer_v_tablice')))
        out[к] = {'inn': i, 'тип': 'событие', 'дата': '', 'описание': обрез('техприсоединение (СиПР): ' + что), 'ссылка': '',
                  'номер': 'СиПР %s стр.%s №%s' % (чисто(r.get('fajl')), чисто(r.get('stranica')), чисто(r.get('nomer_v_tablice'))),
                  'источник_файл': 'SIPR-ZAYAVITELI-INN.csv'}
        СТАТ['событие строк: SIPR-ZAYAVITELI-INN.csv'] += 1
    return list(out.values())


# ---------- патенты ----------
def патенты():
    out = {}
    for r in строки('VAZHNOE-3s-PATENTY.csv'):
        i = инн(r.get('inn'))
        if not i:
            continue
        if (r.get('zapros_slabyy') or '').strip() not in ('', '0', 'False'):
            СТАТ['патент: слабый запрос, пропуск'] += 1
            continue
        н = чисто(r.get('nomer'))
        к = (i, н or норм_url(r.get('ssylka')))
        if not к[1] or к in out:
            continue
        оп = 'патент %s «%s»' % (н, обрез(чисто(r.get('nazvanie')).capitalize() if чисто(r.get('nazvanie')).isupper() else r.get('nazvanie'), 140))
        if чисто(r.get('izobretateli')):
            оп += '; изобретатели: ' + обрез(r.get('izobretateli'), 90)
        оп += '; предприятие упомянуто в тексте патента (патентообладатель не проверен)'
        out[к] = {'inn': i, 'тип': 'патент', 'дата': '', 'описание': обрез(оп), 'ссылка': чисто(r.get('ssylka')), 'номер': н,
                  'источник_файл': 'VAZHNOE-3s-PATENTY.csv'}
    СТАТ['патент выдано'] = len(out)
    return list(out.values())


def main():
    t0 = time.time()
    собрать_стоп()
    эпб_файлы()
    снимок()
    атлас()
    всё = эпб_выдать() + [{k: v for k, v in x.items() if not k.startswith('_')} for x in ОБОР.values()] + опо() + егрз() + события() + патенты()
    всё.sort(key=lambda x: (x['inn'], x['тип'], x['дата']))
    tmp = ВЫХ + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        for x in всё:
            f.write(json.dumps({k: x.get(k, '') for k in ('inn', 'тип', 'дата', 'описание', 'ссылка', 'номер', 'источник_файл')},
                               ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ВЫХ)
    по_типу = collections.Counter(x['тип'] for x in всё)
    инн_типа = collections.defaultdict(set)
    for x in всё:
        инн_типа[x['тип']].add(x['inn'])
    print('===ИТОГ===')
    print(json.dumps({'файл': ВЫХ, 'записей': len(всё), 'ИНН': len({x['inn'] for x in всё}),
                      'по типу': {т: [n, len(инн_типа[т])] for т, n in по_типу.most_common()},
                      'без ссылки': sum(1 for x in всё if not x['ссылка']), 'стоп': sum(СТОП_ПРИЧИНЫ.values()),
                      'стоп причины': СТОП_ПРИЧИНЫ.most_common(12), 'стат': dict(СТАТ.most_common(60)),
                      'сек': round(time.time() - t0)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
