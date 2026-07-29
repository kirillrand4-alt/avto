# -*- coding: utf-8 -*-
"""НОВОСТИ ОТ КОМПАНИИ (переворот news_scan: не от события, а от юрлица).

Идея владельца 2026-07-23. Сейчас news_scan ловит широким неводом любой капекс
и потом резолвит компанию — отсюда тёзки и промахи. Здесь наоборот: берём
компанию из базы обзвона и спрашиваем выдачу адресно:
    "<точное название>" (модернизац | построил | запустил | расширение |
     инвестиц | ввёл | реконструкц)
ИНН известен заранее, резолвить нечего, тёзок нет по построению — но проверять
привязку всё равно надо: выдача возвращает и однофамильцев-юрлиц, и новости про
соседний завод той же отрасли.

Подкоманды:
  targets                 — один проход по базе obzvon_all → цели по выручке
  probe [--n N]           — проба вариантов запроса на нескольких компаниях
  serp --off N --lim M    — сбор выдачи + статей в durable-поток
  measure --a/--b/--c N   — три страта по выручке в одном задании (замер)
  pack --tag X            — пересобрать пачку из потока (если задание убили)
  apply --file a,b,c      — записать классифицированные сигналы в enrich.db
  report | overlap        — цифры ИЗ БАЗЫ, в т.ч. прирост сверх старого невода
  abbrtest | freshtest    — замеры: аббревиатура vs полное имя, фильтр свежести

КАК ЗАПУСКАТЬ (раннер разбирает задания ПО ОДНОМУ, очередь общая с другими
агентами, поэтому panel_file_put на каждый прогон — расточительство):
  1) один раз выложить загрузчик news_from_company_loader.py в C:\sender\_ops
     под именем _newsco_run.py (через runop.py);
  2) дальше код обновлять так: `drop_client.sh up <этот файл>`, но ИМЕННО ПОД
     ИМЕНЕМ newsco_op.py — загрузчик читает
     C:\seostat\drop\drop-storage\newsco_op.py;
  3) запускать одним заданием: panel_py C:\sender\_ops\_newsco_run.py argv=[...].

Классификация статей — ОТДЕЛЬНО и В ПЕСОЧНИЦЕ (news_from_company_classify.py):
провайдерский ключ есть локально, а раннер — узкое место.

Всё durable: поток C:\\seostat\\drop\\newsco_stream.jsonl (flush+fsync),
пачки для скачивания в drop-storage, резюм по stage_log в enrich.db.
"""
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS        # noqa: E402  _get (bypass прокси + TLS), FULLTEXT_CAP
import enrich_contacts as EC  # noqa: E402  _fetch_site/_раскодировать/_текст/_фио
import enrich_db as EDB       # noqa: E402

ДРОП = r'C:\seostat\drop'
ХРАН = os.path.join(ДРОП, 'drop-storage')
ПОТОК = os.path.join(ДРОП, 'newsco_stream.jsonl')
ЦЕЛИ = os.path.join(ДРОП, 'newsco_targets.jsonl')

# ------------------------------------------------------------------ аргументы
А = sys.argv[1:]
КОМАНДА = А[0] if А else 'probe'


def арг(имя, по_умолчанию=None, тип=str):
    if имя in А:
        return тип(А[А.index(имя) + 1])
    return по_умолчанию


# ------------------------------------------------------------------ имя → ядро
_ОПФ_НАЧАЛО = re.compile(
    r'^(ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ|АКЦИОНЕРНОЕ ОБЩЕСТВО|'
    r'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО|ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО|'
    r'ОТКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО|НЕПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО|'
    r'ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ УНИТАРНОЕ ПРЕДПРИЯТИЕ|'
    r'ООО|АО|ПАО|ЗАО|ОАО|НАО|ГУП|МУП|ФГУП|АНО|ИП)\s+', re.I)


_АББР = re.compile(r'^[А-ЯЁA-Z0-9-]{2,5}$')


def имя_для_запроса(krat, poln):
    """Чем спрашивать выдачу. КРАТКОЕ имя у 13 компаний из 34 в верхнем страте —
    аббревиатура («ТСМ», «ДИМ», «ВАД», «БСК»), и запрос «"ТСМ" (модернизация…)»
    это ровно тот тёзка-риск, ради устранения которого затевался переворот; к
    тому же по аббревиатуре нечем доказать привязку — слов длиной 4+ в ней нет.
    У 12 из этих 13 ПОЛНОЕ имя несёт настоящее название
    (ООО "ТСМ" = «ТРАНССТРОЙМЕХАНИЗАЦИЯ»). Берём полное, когда краткое —
    аббревиатура, а полное даёт более длинное содержательное ядро.
    """
    я_к, я_п = ядро_имени(krat), ядро_имени(poln)
    if _АББР.match(я_к.replace(' ', '')) and len(я_п) > len(я_к) + 2:
        return я_п
    return я_к or я_п


def ядро_имени(s):
    """Название для точного запроса: то, что в кавычках, иначе — без ОПФ.

    ВЛОЖЕННЫЕ КАВЫЧКИ (поймано на пробе): у `ООО "ПИВОВАРЕННАЯ КОМПАНИЯ
    "БАЛТИКА"` нежадный разбор брал только «ПИВОВАРЕННАЯ КОМПАНИЯ» и терял
    САМО ИМЯ — запрос уходил по родовому слову, а это ровно тот тёзка-риск,
    ради устранения которого затевался переворот. Берём от ПЕРВОЙ кавычки до
    ПОСЛЕДНЕЙ и вычищаем внутренние.
    """
    s = (s or '').strip()
    кав = '\u00ab\u00bb"\u201c\u201d\u201e'
    поз = [k for k, ch in enumerate(s) if ch in кав]
    if len(поз) >= 2 and поз[-1] - поз[0] > 2:
        ядро = s[поз[0] + 1:поз[-1]]
    else:
        ядро = _ОПФ_НАЧАЛО.sub('', s)
    ядро = ''.join(' ' if ch in кав else ch for ch in ядро)
    return re.sub(r'\s+', ' ', ядро).strip(" '-")


# ------------------------------------------------------------------ xmlriver
_USER = os.environ.get('XMLRIVER_USER', '')
_KEY = os.environ.get('XMLRIVER_KEY', '')
ЗАПРОСОВ = [0]   # счётчик оплаченных обращений (25₽/1000)


def серп(запрос, движок='yandex', сырой=False):
    """Один оплаченный запрос в xmlriver. Возвращает список {url,title,passage}."""
    if not (_USER and _KEY):
        return ([], '') if сырой else []
    if движок == 'yandex':
        u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(_USER)
             + '&key=' + urllib.parse.quote(_KEY) + '&domain=ru&device=desktop'
             + '&query=' + urllib.parse.quote(запрос))
    else:
        u = ('http://xmlriver.com/search/xml?user=' + urllib.parse.quote(_USER)
             + '&key=' + urllib.parse.quote(_KEY)
             + '&query=' + urllib.parse.quote(запрос))
    тело = ''
    for att in range(3):
        ЗАПРОСОВ[0] += 1
        тело = NS._get(u, timeout=45)
        if тело and 'Выполните перезапрос' not in тело and '<error' not in тело[:400]:
            break
        time.sleep(1.5 + att * 2)
    док = []
    for d in re.findall(r'<doc>(.*?)</doc>', тело or '', re.S):
        def g(tag, d=d):
            m = re.search(r'<%s[^>]*>(.*?)</%s>' % (tag, tag), d, re.S)
            return re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', '', m.group(1)).strip() if m else ''
        пасс = ' '.join(re.sub(r'<[^>]+>', '', p).strip()
                        for p in re.findall(r'<passage>(.*?)</passage>', d, re.S))
        u2 = g('url')
        if u2:
            док.append({'url': u2.replace('&amp;', '&'), 'title': g('title'),
                        'passage': пасс or g('headline'), 'pubdate': g('pubDate') or g('modtime')})
    return (док, тело) if сырой else док


# --------------------------------------------------------- капекс-предфильтр
# тот же смысл, что NS._CAPEX_KW, но заточен под «событие компании», а не ленту
_КАПЕКС = re.compile(
    r'модерниз|реконструкц|построил|построен|строит|стройк|возвед|'
    r'запуст|запуск|ввёл|ввел|введ[её]н|ввод\w* в эксплуатац|открыл|открыт\w+ (?:цех|лини|производств)|'
    r'расшир|нов\w+ (?:цех|лини|производств|корпус|завод|участок)|'
    r'инвестиц|инвестир|вложил|вложен|капвложен|млрд руб|млн руб|'
    r'техперевооруж|перевооружен|обновил\w* парк|закупил\w* оборудован|'
    r'увеличил\w* мощност|нарастил\w* мощност|производственн\w+ площадк', re.I)
# золото: наше оборудование прямо названо
_НАШЕ = re.compile(
    r'компрессор|компрессорн|воздухоразделительн|азотн\w+ (?:станц|генератор|установк)|'
    r'кислородн\w+ (?:станц|генератор|установк)|генератор\w* азота|генератор\w* кислорода|'
    r'ВРУ\b|АГНКС|осушител\w+ воздуха|пневмосет|сжат\w+ воздух|'
    r'котельн|компрессорн\w+ станц|фотосепаратор|рентген-инспекц', re.I)
# домены, где «новости компании» — это выписка из ЕГРЮЛ, вакансии или каталог
_МУСОР_ДОМЕН = re.compile(
    r'checko|rusprofile|list-org|audit-it|zachestnyibiznes|sbis\.ru|kontur|'
    r'companies\.rbc|synapsenet|vypiska|egrul|nalog\.ru|sbis|testfirm|bo\.nalog|'
    r'hh\.ru|superjob|rabota|zarplata|trud\.com|vakans|avito|ozon|wildberries|'
    r'youtube|pinterest|ok\.ru/video|tiktok|zakupki\.gov|tenderguru|bicotender|'
    r'seldon|tender|torgi|rostender|damia|spark-interfax|casebook|kad\.arbitr|'
    r'arbitr\.ru|sudact|pravo\.ru|otzyv|отзыв|prodoctorov|2gis|yell\.ru|'
    r'orgpage|spravka|katalog|allbiz|pulscen|tiu\.ru|blizko|satom|'
    r'bidzaar|roseltorg|b2b-center|fabrikant|sberbank-ast|'
    r'consultant\.ru|garant\.ru|normacs|docs\.cntd|pravo\.gov|'
    r'wikipedia|wikimapia|studfile|dissercat|cyberleninka', re.I)


def мусорный(url):
    return bool(_МУСОР_ДОМЕН.search(url or ''))


# ---------------------------------------------------------------- цели из базы
def построить_цели():
    import csv
    p = EC._get_base()
    if not p:
        print(json.dumps({'ошибка': 'база не найдена'}, ensure_ascii=False))
        return
    INN, KRAT, POLN, ADDR, REG, OKVED, PHONES, SITE = 1, 5, 6, 9, 10, 16, 18, 20
    # 24 «Выручка» и 34 «Выручка, руб.» — ДВЕ разные колонки. Считаем обе:
    # проба показала в топе по [34] две районные больницы с «546» и «202 млрд»,
    # чего быть не может. Сохраняем обе, ранжируем по [34], но пишем rev24 —
    # чтобы расхождение было видно, а не молча портило приоритет.
    REV, REV24, SSC = 34, 24, 27
    try:
        csv.field_size_limit(2 ** 18)
    except Exception:  # noqa: BLE001
        pass
    строк, взято = 0, []
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')
        next(rd, None)
        while True:
            try:
                row = next(rd)
            except StopIteration:
                break
            except Exception:  # noqa: BLE001
                continue
            строк += 1
            if len(row) <= REV:
                continue
            def _ч(i):
                try:
                    return float(re.sub(r'[^\d.]', '', (row[i] or '0').replace(',', '.')) or 0)
                except Exception:  # noqa: BLE001
                    return 0.0
            rev, rev24, ssc = _ч(REV), _ч(REV24), _ч(SSC)
            addr = row[ADDR] or ''
            mc = re.search(r'(?:\bг\.\s*|\bгород\s+|\bпгт\.?\s*|\bс\.\s*|\bрп\.?\s*)'
                           r'([А-ЯЁ][А-Яа-яЁё-]+)', addr)
            взято.append({'inn': (row[INN] or '').strip(),
                          'krat': (row[KRAT] or '').strip(),
                          'poln': (row[POLN] or '').strip(),
                          'city': mc.group(1) if mc else '',
                          'region': (row[REG] or '').strip(),
                          'okved': (row[OKVED] or '').strip(),
                          'site': (row[SITE] or '').strip(),
                          'rev': rev, 'rev24': rev24, 'ssc': ssc})
    взято.sort(key=lambda x: -x['rev'])
    вёдра = {'>=10 млрд': 0, '2-10 млрд': 0, '0.8-2 млрд (средний)': 0,
             '0.2-0.8 млрд': 0, '0.12-0.2 млрд': 0, '<0.12 млрд': 0, 'нет выручки': 0}
    for c in взято:
        r = c['rev']
        k = ('нет выручки' if r <= 0 else '>=10 млрд' if r >= 1e10
             else '2-10 млрд' if r >= 2e9 else '0.8-2 млрд (средний)' if r >= 8e8
             else '0.2-0.8 млрд' if r >= 2e8 else '0.12-0.2 млрд' if r >= 1.2e8
             else '<0.12 млрд')
        вёдра[k] += 1
    топ = взято[:30000]
    with open(ЦЕЛИ, 'w', encoding='utf-8') as f:
        for c in топ:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as z:
        z.write('\n'.join(json.dumps(c, ensure_ascii=False) for c in топ).encode('utf-8'))
    with open(os.path.join(ХРАН, 'newsco_targets.jsonl.gz'), 'wb') as f:
        f.write(buf.getvalue())
        f.flush()
        os.fsync(f.fileno())
    итог = {'строк_в_базе': строк, 'записано_целей': len(топ), 'вёдра': вёдра,
            'макс_выручка': взято[0]['rev'] if взято else 0,
            'примеры': [{'krat': c['krat'], 'ядро': ядро_имени(c['krat'] or c['poln']),
                         'rev': c['rev']} for c in взято[:5]]}
    print(json.dumps(итог, ensure_ascii=False)[:1500])
    print(json.dumps(итог, ensure_ascii=False)[:1500])


def цели(off=0, lim=50, мин=None, макс=None):
    out = []
    if not os.path.exists(ЦЕЛИ):
        return out
    with open(ЦЕЛИ, encoding='utf-8') as f:
        for line in f:
            try:
                c = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if мин is not None and c['rev'] < мин:
                continue
            if макс is not None and c['rev'] >= макс:
                continue
            out.append(c)
    return out[off:off + lim]


# ------------------------------------------------------------------ ПРОБА
_ВАР = {
    'v1_or': '"{n}" (модернизация OR построит OR запустит OR расширяет OR инвестирует OR реконструкция)',
    'v2_pipe': '"{n}" (модернизация | строительство | запуск | расширение | инвестиции | реконструкция)',
    'v3_prosto': '{n} модернизация производства новый цех',
}


def проба(n=6):
    цел = цели(0, n)
    рез = {'компаний': len(цел), 'варианты': {}, 'по_компаниям': []}
    дамп = {'xml': ''}

    def одна(i_c):
        i, c = i_c
        имя = ядро_имени(c['krat'] or c['poln'])
        зап = {}
        for ключ, шаб in _ВАР.items():
            q = шаб.format(n=имя)
            if i == 0 and ключ == 'v1_or':
                d, сырой = серп(q, 'yandex', сырой=True)
                дамп['xml'] = (сырой or '')[:1800]
            else:
                d = серп(q, 'yandex')
            чист = [x for x in d if not мусорный(x['url'])]
            капекс = [x for x in чист
                      if _КАПЕКС.search((x['title'] or '') + ' ' + (x['passage'] or ''))]
            зап[ключ] = {'всего': len(d), 'чистых': len(чист), 'капекс': len(капекс),
                         'примеры': [{'t': x['title'][:90], 'u': x['url'][:95],
                                      'p': (x['passage'] or '')[:130]} for x in капекс[:2]]}
        return {'инн': c['inn'], 'имя': имя[:60],
                'выручка_млрд': round(c['rev'] / 1e9, 2), 'запросы': зап}

    with ThreadPoolExecutor(max_workers=4) as ex:
        рез['по_компаниям'] = list(ex.map(одна, list(enumerate(цел))))
    for стр in рез['по_компаниям']:
        for ключ, з in стр['запросы'].items():
            v = рез['варианты'].setdefault(ключ, {'всего': 0, 'чистых': 0, 'капекс': 0,
                                                  'компаний_с_капексом': 0})
            v['всего'] += з['всего']
            v['чистых'] += з['чистых']
            v['капекс'] += з['капекс']
            if з['капекс']:
                v['компаний_с_капексом'] += 1
    сырой_дамп = дамп['xml']
    рез['оплачено_запросов'] = ЗАПРОСОВ[0]
    рез['стоимость_руб'] = round(ЗАПРОСОВ[0] * 0.025, 3)
    рез['сырой_xml_голова'] = сырой_дамп
    s = json.dumps(рез, ensure_ascii=False, indent=1)
    print(s[:9000])
    print(json.dumps({'итог': рез['варианты'], 'оплачено': ЗАПРОСОВ[0]}, ensure_ascii=False))


# ------------------------------------------------------------------ статьи
_ДАТА_URL = re.compile(r'/(20\d\d)[/\-_.](\d{1,2})(?:[/\-_.](\d{1,2}))?/')
_ДАТА_META = re.compile(
    r'(?:article:published_time|datePublished|publish[-_]?date|itemprop="datePublished")'
    r'[^>]{0,80}?(20\d\d)-(\d{2})-(\d{2})', re.I)
_ДАТА_TIME = re.compile(r'<time[^>]*datetime="(20\d\d)-(\d{2})-(\d{2})', re.I)
_МЕС = {'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'май': 5, 'июн': 6, 'июл': 7,
        'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12}
_ДАТА_РУС = re.compile(r'(\d{1,2})\s+([а-яё]{3})[а-яё]*\.?\s+(20\d\d)', re.I)


def дата_страницы(html, url, текст=''):
    """Дата публикации: meta → <time> → URL → русская дата в начале текста."""
    for rx in (_ДАТА_META, _ДАТА_TIME):
        m = rx.search(html or '')
        if m:
            return '%s-%s-%s' % (m.group(1), m.group(2), m.group(3))
    m = _ДАТА_URL.search(url or '')
    if m:
        мес = int(m.group(2))
        if 1 <= мес <= 12:
            return '%s-%02d-%02d' % (m.group(1), мес, int(m.group(3) or 1))
    m = _ДАТА_РУС.search((текст or '')[:1500])
    if m:
        мес = _МЕС.get(m.group(2).lower())
        if мес:
            return '%s-%02d-%02d' % (m.group(3), мес, int(m.group(1)))
    return ''


def возраст_мес(дата):
    if not дата:
        return None
    try:
        import datetime as dt
        d = dt.date(*[int(x) for x in дата.split('-')])
        return round((dt.date.today() - d).days / 30.44, 1)
    except Exception:  # noqa: BLE001
        return None


def быстрый_фетч(url, timeout=12):
    """Текст страницы БЕЗ капча-фолбэка. Причина: EC._fetch_site при блоке уходит
    в VC._fetch с решателем Turnstile, и одна страница съедает минуты — на прогоне
    из 34 компаний этого хватило, чтобы выбрать весь бюджет задания. Кодировку
    берём через EC._раскодировать (прямой utf-8 уже стоил ложного нуля)."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': NS.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with EC._DIRECT.open(req, timeout=timeout) as r:
            try:
                raw = r.read(400000)
            except Exception as e:  # noqa: BLE001
                raw = getattr(e, 'partial', b'') or b''
            return EC._раскодировать(raw, r.headers.get('Content-Type', ''))
    except Exception:  # noqa: BLE001
        return ''


def токены_имени(имя):
    return [t for t in re.findall(r'[а-яёa-z0-9]+', (имя or '').lower())
            if len(t) >= 4 and not NS._SRC_OPF.match(t)]


def привязка(текст, инн, имя, полное):
    """Механическое ДОКАЗАТЕЛЬСТВО, что страница про эту компанию.
    инн_на_странице — сильнейшее; полное_имя — сильное; ядро — слабое (тёзки!)."""
    t = (текст or '').lower()
    if not t:
        return {'уровень': 'нет_текста', 'инн': False, 'полное': False, 'ядро': 0}
    инн_есть = bool(инн) and инн in t
    полн = ' '.join(токены_имени(полное))
    полное_есть = bool(полн) and all(w[:6] in t for w in полн.split()[:6]) and len(полн.split()) >= 2
    ток = токены_имени(имя)
    попало = sum(1 for w in ток if w[:5] in t)
    ур = ('инн' if инн_есть else 'полное_имя' if полное_есть
          else 'ядро' if ток and попало == len(ток)
          else 'частично' if попало else 'нет')
    return {'уровень': ур, 'инн': инн_есть, 'полное': полное_есть,
            'ядро': попало, 'ядро_всего': len(ток)}


ЗАПРОС = ('"{n}" (модернизация OR построит OR запустит OR расширяет OR '
          'инвестирует OR реконструкция)')


def сбор(off, lim, мин=None, макс=None, тег='b0', движки=('yandex',), статей=3,
         воркеров=6, бюджет=1500):
    цел = цели(off, lim, мин, макс)
    # РЕЗЮМ по durable-потоку: прошлый прогон убило таймаутом задания на страте B,
    # и без этого пришлось бы платить за уже сделанные запросы заново.
    сделано = set()
    if os.path.exists(ПОТОК):
        for line in open(ПОТОК, encoding='utf-8'):
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get('тег') == тег:
                сделано.add(r.get('inn'))
    цел = [c for c in цел if c['inn'] not in сделано]
    db = EDB.EnrichDB()
    поток = open(ПОТОК, 'a', encoding='utf-8')
    import threading
    lock = threading.Lock()
    сч = {'компаний': 0, 'с_выдачей': 0, 'после_чистки': 0, 'кандидатов': 0,
          'скачано': 0, 'пусто': 0, 'привязка_ок': 0, 'наше_оборудование': 0}
    пачка = []
    t0 = time.time()

    def одна(c):
        if time.time() - t0 > бюджет:
            return
        имя = имя_для_запроса(c['krat'], c['poln'])
        if len(имя) < 3:
            return
        док = []
        for дв in движки:
            док += серп(ЗАПРОС.format(n=имя), дв)
        with lock:
            сч['компаний'] += 1
            if док:
                сч['с_выдачей'] += 1
        чист = []
        видел = set()
        for x in док:
            k = NS._norm_url(x['url'])
            if k in видел or мусорный(x['url']):
                continue
            видел.add(k)
            чист.append(x)
        капекс = [x for x in чист
                  if _КАПЕКС.search((x['title'] or '') + ' ' + (x['passage'] or ''))]
        with lock:
            сч['после_чистки'] += len(чист)
            сч['кандидатов'] += len(капекс)
        статьи = []
        for x in капекс[:статей]:
            if time.time() - t0 > бюджет:
                break
            html, текст = '', ''
            try:
                html = быстрый_фетч(x['url'])
                if html and not EC._looks_blocked(html):
                    текст = EC._текст(html)
            except Exception:  # noqa: BLE001
                pass
            дата = дата_страницы(html, x['url'], текст)
            прив = привязка(текст or ((x['title'] or '') + ' ' + (x['passage'] or '')),
                            c['inn'], имя, c['poln'] or c['krat'])
            наше = bool(_НАШЕ.search(текст or x['passage'] or ''))
            with lock:
                if текст:
                    сч['скачано'] += 1
                else:
                    сч['пусто'] += 1
                if прив['уровень'] in ('инн', 'полное_имя', 'ядро'):
                    сч['привязка_ок'] += 1
                if наше:
                    сч['наше_оборудование'] += 1
            статьи.append({'url': x['url'], 'title': x['title'],
                           'passage': (x['passage'] or '')[:400],
                           'дата': дата, 'возраст_мес': возраст_мес(дата),
                           'привязка': прив, 'наше': наше,
                           'текст': (текст or '')[:7000], 'символов': len(текст or '')})
        зап = {'inn': c['inn'], 'имя': имя, 'krat': c['krat'], 'poln': c['poln'],
               'город': c['city'], 'регион': c['region'], 'оквэд': c['okved'],
               'сайт': c['site'], 'выручка': c['rev'],
               'запрос': ЗАПРОС.format(n=имя), 'выдача': len(док),
               'чистых': len(чист), 'капекс_кандидатов': len(капекс),
               'статьи': статьи, 'тег': тег, 'ts': int(time.time())}
        with lock:
            поток.write(json.dumps(зап, ensure_ascii=False) + '\n')
            поток.flush()
            os.fsync(поток.fileno())
            пачка.append(зап)
            try:
                db.mark_stage(c['inn'], 'newsco_serp',
                                 'выдача=%d кандидатов=%d статей=%d'
                                 % (len(док), len(капекс), len(статьи)))
            except Exception:  # noqa: BLE001
                pass

    with ThreadPoolExecutor(max_workers=воркеров) as ex:
        list(ex.map(одна, цел))
    try:
        db.cx.commit()
    except Exception:  # noqa: BLE001
        pass
    поток.close()
    имя_ф = 'newsco_batch_%s.json.gz' % тег
    # пачку собираем ИЗ ПОТОКА, а не из накопителя в памяти: так в gz попадает и то,
    # что сделал прошлый (убитый) прогон, а не только текущий кусок
    все, видел = [], set()
    for line in open(ПОТОК, encoding='utf-8'):
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if r.get('тег') == тег and r['inn'] not in видел:
            видел.add(r['inn'])
            все.append(r)
    пачка = все
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb') as z:
        z.write(json.dumps(пачка, ensure_ascii=False).encode('utf-8'))
    with open(os.path.join(ХРАН, имя_ф), 'wb') as f:
        f.write(buf.getvalue())
        f.flush()
        os.fsync(f.fileno())
    итог = {'тег': тег, 'off': off, 'lim': lim, 'пропущено_резюмом': len(сделано),
            'в_пачке_всего': len(пачка), 'счётчики': сч,
            'оплачено_запросов': ЗАПРОСОВ[0],
            'стоимость_руб': round(ЗАПРОСОВ[0] * 0.025, 3),
            'секунд': round(time.time() - t0), 'пачка': имя_ф,
            'байт_gz': len(buf.getvalue())}
    print(json.dumps(итог, ensure_ascii=False))
    print(json.dumps(итог, ensure_ascii=False))


# ------------------------------------------------------------------ ЗАПИСЬ
def применить(файл, тег='b0'):
    данные = {'сигналы': [], 'люди': []}
    for ф in (файл or '').split(','):
        ф = ф.strip()
        if not ф:
            continue
        путь = ф if os.path.exists(ф) else os.path.join(ХРАН, ф)
        d = json.load(open(путь, encoding='utf-8'))
        данные['сигналы'] += d.get('сигналы') or []
        данные['люди'] += d.get('люди') or []
    db = EDB.EnrichDB()
    жур = open(os.path.join(ДРОП, 'newsco_applied.jsonl'), 'a', encoding='utf-8')
    сч = {'сигналов': 0, 'людей': 0, 'компаний': 0, 'пропущено': 0}
    комп = set()
    for s in данные.get('сигналы', []):
        инн = str(s.get('inn') or '')
        if not инн:
            сч['пропущено'] += 1
            continue
        try:
            db.upsert_company(инн, name=s.get('name') or '', okved=s.get('okved') or '',
                              region=s.get('region') or '')
        except Exception:  # noqa: BLE001
            pass
        что = s.get('what') or ''
        д = s.get('date') or ''
        в = возраст_мес(д)
        метка = (' [новость %s%s]' % (д, ', %d мес назад' % round(в) if в is not None else '')
                 if д else ' [дата не определена]')
        if s.get('equipment'):
            метка = ' [%s]' % s['equipment'] + метка
        try:
            db.add_signal(инн, source='новости от компании',
                          event_type=s.get('event_type') or '',
                          what=(что + метка)[:900], sum=str(s.get('sum') or ''),
                          source_url=s.get('url') or '',
                          hotness=int(s.get('hotness') or 0), ts=д)
            сч['сигналов'] += 1
            комп.add(инн)
            жур.write(json.dumps(s, ensure_ascii=False) + '\n')
        except Exception as e:  # noqa: BLE001
            сч['пропущено'] += 1
            жур.write(json.dumps({'ошибка': str(e)[:120], 'зап': s}, ensure_ascii=False) + '\n')
        try:
            db.mark_stage(инн, 'newsco_signal', (s.get('event_type') or '')[:60])
        except Exception:  # noqa: BLE001
            pass
    for p in данные.get('люди', []):
        инн = str(p.get('inn') or '')
        фио, пост = (p.get('person') or '').strip(), (p.get('post') or '').strip()
        if not (инн and фио and пост):
            continue
        try:
            db.add_person(инн, фио, post=пост, source='новости от компании',
                          source_url=p.get('url') or '')
            сч['людей'] += 1
            жур.write(json.dumps(p, ensure_ascii=False) + '\n')
        except Exception:  # noqa: BLE001
            pass
    сч['компаний'] = len(комп)
    жур.flush()
    os.fsync(жур.fileno())
    жур.close()
    try:
        db.cx.commit()
    except Exception:  # noqa: BLE001
        pass
    из_базы = отчёт_из_базы(db)
    итог = {'записано': сч, 'ИЗ_БАЗЫ': из_базы}
    print(json.dumps(итог, ensure_ascii=False))
    print(json.dumps(итог, ensure_ascii=False))


def пересечение():
    """Что переворот добавил СВЕРХ старого невода: сколько компаний получили
    сигнал впервые, а сколько уже были в signals от news_scan."""
    db = EDB.EnrichDB()
    e = db.cx
    свои = {r[0] for r in e.execute(
        "SELECT DISTINCT inn FROM signals WHERE source='новости от компании'")}
    чужие = {r[0] for r in e.execute(
        "SELECT DISTINCT inn FROM signals WHERE source!='новости от компании'")}
    вся_база_комп = e.execute('SELECT count(*) FROM companies').fetchone()[0]
    return {'компаний_от_компании': len(свои),
            'из_них_уже_были_в_signals_от_невода': len(свои & чужие),
            'НОВЫХ_компаний_с_сигналом': len(свои - чужие),
            'компаний_в_signals_от_невода_всего': len(чужие),
            'компаний_в_companies': вся_база_комп}


def отчёт_из_базы(db=None):
    db = db or EDB.EnrichDB()
    e = db.cx
    q = "source='новости от компании'"
    из = {}
    из['сигналов'] = e.execute('SELECT count(*) FROM signals WHERE %s' % q).fetchone()[0]
    из['компаний_с_сигналом'] = e.execute(
        'SELECT count(DISTINCT inn) FROM signals WHERE %s' % q).fetchone()[0]
    из['людей'] = e.execute(
        "SELECT count(*) FROM people WHERE source='новости от компании'").fetchone()[0]
    из['компаний_с_людьми'] = e.execute(
        "SELECT count(DISTINCT inn) FROM people WHERE source='новости от компании'").fetchone()[0]
    техроли = ','.join("'%s'" % r for r in EDB.EnrichDB.TECH_ROLES)
    из['техЛПР'] = e.execute(
        "SELECT count(*) FROM people WHERE source='новости от компании' AND role IN (%s)"
        % техроли).fetchone()[0]
    из['сигналов_наше_оборудование'] = e.execute(
        "SELECT count(*) FROM signals WHERE %s AND (what LIKE '%%компрессор%%' OR "
        "what LIKE '%%азот%%' OR what LIKE '%%кислород%%' OR what LIKE '%%воздухоразделит%%' "
        "OR what LIKE '%%котельн%%' OR what LIKE '%%сжат%%возду%%')" % q).fetchone()[0]
    из['по_горячести'] = dict(e.execute(
        'SELECT hotness, count(*) FROM signals WHERE %s GROUP BY hotness' % q).fetchall())
    из['примеры'] = [{'inn': r[0], 'what': (r[1] or '')[:150], 'url': (r[2] or '')[:110],
                      'hot': r[3]} for r in e.execute(
        'SELECT inn, what, source_url, hotness FROM signals WHERE %s '
        'ORDER BY hotness DESC LIMIT 6' % q).fetchall()]
    return из


if __name__ == '__main__':
    t0 = time.time()
    sys.stderr.write('newsco %s старт\n' % КОМАНДА)
    if КОМАНДА == 'targets':
        построить_цели()
    elif КОМАНДА == 'probe':
        if not os.path.exists(ЦЕЛИ):
            sys.stderr.write('целей нет — строю из базы\n')
            построить_цели()
        проба(int(арг('--n', 6)))
    elif КОМАНДА == 'serp':
        if '--rebuild' in А or not os.path.exists(ЦЕЛИ):
            построить_цели()
        сбор(int(арг('--off', 0)), int(арг('--lim', 50)),
             float(арг('--min')) if арг('--min') else None,
             float(арг('--max')) if арг('--max') else None,
             арг('--tag', 'b0'),
             tuple((арг('--engines', 'yandex')).split(',')),
             int(арг('--articles', 3)), int(арг('--workers', 6)),
             int(арг('--budget', 1150)))
    elif КОМАНДА == 'measure':
        # ЗАМЕР В ОДНО ЗАДАНИЕ: раннер выполняет по одному, очередь общая с
        # другими агентами — три страта отдельными джобами стояли бы час.
        if '--rebuild' in А or not os.path.exists(ЦЕЛИ):
            построить_цели()
        страты = [('A', 0, int(арг('--a', 34)), None, None),
                  ('B', 0, int(арг('--b', 33)), 8e8, 2e9),
                  ('C', 0, int(арг('--c', 33)), 2e8, 8e8)]
        всего = int(арг('--budget', 1000))
        for i, (тег, off, lim, мин, макс) in enumerate(страты):
            ост = всего - int(time.time() - t0)
            if ост < 60:
                sys.stderr.write('бюджет кончился, страт %s пропущен\n' % тег)
                break
            сбор(off, lim, мин, макс, тег, ('yandex',),
                 int(арг('--articles', 3)), int(арг('--workers', 6)), ост)
    elif КОМАНДА == 'freshtest':
        # Свежесть: из 62 сигналов замера только 12 моложе года, 20 старше трёх
        # лет — то есть невод тащит ИСТОРИЮ компании, а не повод для звонка.
        # Проверяем, что даёт тот же запрос с яндексовым оператором date:>.
        import datetime as _dt
        дней = int(арг('--days', 365))
        отсечка = (_dt.date.today() - _dt.timedelta(days=дней)).strftime('%Y%m%d')
        цел = цели(0, int(арг('--n', 34)))
        сч = {'компаний': 0, 'без_фильтра_капекс': 0, 'с_фильтром_капекс': 0,
              'компаний_без': 0, 'компаний_с': 0}
        прим = []

        def одна_f(c):
            имя = имя_для_запроса(c['krat'], c['poln'])
            баз = ЗАПРОС.format(n=имя)
            рез = {}
            for ключ, q in (('без', баз), ('с', баз + ' date:>' + отсечка)):
                д = серп(q, 'yandex')
                ч = [x for x in д if not мусорный(x['url'])]
                к = [x for x in ч if _КАПЕКС.search((x['title'] or '') + ' '
                                                    + (x['passage'] or ''))]
                рез[ключ] = (len(д), len(к), [x['title'][:60] for x in к[:2]])
            return c, рез

        with ThreadPoolExecutor(max_workers=5) as ex:
            for c, рез in ex.map(одна_f, цел):
                сч['компаний'] += 1
                сч['без_фильтра_капекс'] += рез['без'][1]
                сч['с_фильтром_капекс'] += рез['с'][1]
                сч['компаний_без'] += 1 if рез['без'][1] else 0
                сч['компаний_с'] += 1 if рез['с'][1] else 0
                if len(прим) < 6 and рез['с'][1]:
                    прим.append({'имя': c['krat'][:34], 'свежих': рез['с'][1],
                                 'заголовки': рез['с'][2]})
        итог = {'дней': дней, 'счётчики': сч, 'оплачено': ЗАПРОСОВ[0],
                'примеры': прим}
        print(json.dumps(итог, ensure_ascii=False)[:3500])
        print(json.dumps({'дней': дней, 'счётчики': сч, 'оплачено': ЗАПРОСОВ[0]},
                         ensure_ascii=False))
    elif КОМАНДА == 'abbrtest':
        # сколько теряет запрос по аббревиатуре против запроса по полному имени
        цел = [c for c in цели(0, 400)
               if _АББР.match(ядро_имени(c['krat']).replace(' ', ''))][:int(арг('--n', 12))]
        итог = []
        for c in цел:
            я_к, я_п = ядро_имени(c['krat']), ядро_имени(c['poln'])
            стр = {'inn': c['inn'], 'аббр': я_к, 'полное': я_п}
            for ключ, имя in (('аббр', я_к), ('полное', я_п)):
                д = серп(ЗАПРОС.format(n=имя), 'yandex')
                ч = [x for x in д if not мусорный(x['url'])]
                к = [x for x in ч if _КАПЕКС.search((x['title'] or '') + ' '
                                                    + (x['passage'] or ''))]
                # доказуемость: в заголовке/пассаже есть все содержательные слова
                текст = ' '.join(((x['title'] or '') + ' ' + (x['passage'] or ''))
                                 for x in к).lower()
                ток = токены_имени(имя)
                стр[ключ] = {'выдача': len(д), 'капекс': len(к),
                             'слова_имени_есть': bool(ток) and all(w[:5] in текст for w in ток)}
            итог.append(стр)
        свод = {'компаний': len(итог),
                'капекс_по_аббр': sum(x['аббр']['капекс'] for x in итог),
                'капекс_по_полному': sum(x['полное']['капекс'] for x in итог),
                'доказуемо_аббр': sum(1 for x in итог if x['аббр']['слова_имени_есть']),
                'доказуемо_полное': sum(1 for x in итог if x['полное']['слова_имени_есть']),
                'оплачено': ЗАПРОСОВ[0], 'строки': итог[:12]}
        print(json.dumps(свод, ensure_ascii=False)[:4000])
        print(json.dumps({k: v for k, v in свод.items() if k != 'строки'},
                         ensure_ascii=False))
    elif КОМАНДА == 'pack':
        тег = арг('--tag', 'A')
        зап, видел = [], set()
        for line in open(ПОТОК, encoding='utf-8'):
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get('тег') != тег or r['inn'] in видел:
                continue
            видел.add(r['inn'])
            зап.append(r)
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as z:
            z.write(json.dumps(зап, ensure_ascii=False).encode('utf-8'))
        with open(os.path.join(ХРАН, 'newsco_batch_%s.json.gz' % тег), 'wb') as f:
            f.write(buf.getvalue())
            f.flush()
            os.fsync(f.fileno())
        итог = {'тег': тег, 'компаний_в_потоке': len(зап),
                'статей': sum(len(r.get('статьи') or []) for r in зап),
                'байт_gz': len(buf.getvalue())}
        print(json.dumps(итог, ensure_ascii=False))
        print(json.dumps(итог, ensure_ascii=False))
    elif КОМАНДА == 'apply':
        применить(арг('--file', 'newsco_signals.json'), арг('--tag', 'b0'))
    elif КОМАНДА == 'overlap':
        s2 = json.dumps(пересечение(), ensure_ascii=False)
        print(s2)
        print(s2)
    elif КОМАНДА == 'report':
        s = json.dumps(отчёт_из_базы(), ensure_ascii=False, indent=1)
        print(s)
        print(s)
    else:
        print(json.dumps({'ошибка': 'неизвестная команда %s' % КОМАНДА}, ensure_ascii=False))
    sys.stderr.write('newsco %s готово за %.0fс, запросов %d\n'
                     % (КОМАНДА, time.time() - t0, ЗАПРОСОВ[0]))
