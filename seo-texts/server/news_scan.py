# -*- coding: utf-8 -*-
"""news_scan v2 — триггерные лиды из новостей, МУЛЬТИ-ИСТОЧНИК.

Карта источников (из 6 линз, NEWS-LEADS.md):
  Тир-1 гиперлокал: районные паблики ВК, группы ОК, райгазеты, райадминистрации.
  Тир-2 реестры:    ФРП (займы=капекс), ГИСП/СПИК, ОЭЗ/ТОР/индустриальные парки.
  Тир-3 тендеры:    zakupki.gov.ru (ОКПД2 28.13 + стройка цеха/корпуса).
  Тир-4 агрегаторы: Google News RSS, деловые/отраслевые СМИ.
  Тир-5 следы:      hh.ru (всплеск вакансий = расширение), 2ГИС/карты.

Конвейер (единый для всех коллекторов):
  собрать items{title,link,source_name,published,tier,collector} -> провайдер
  извлекает КАПЕКС-событие -> DaData (имя->ИНН->ОКВЭД-фильтр) -> опц. обогащение
  контактов (enrich_contacts: сайт->роль-email, РФ-IP + обход Turnstile) -> скоринг.
  У КАЖДОГО события source_url обязателен (человек верифицирует).

Капча: сайты компаний/гиперлокал за Cloudflare/капчей — только СЕРВЕР (РФ-IP +
CapMonster). Поэтому боевой прогон — задача раннера (task=news_scan), не песочница.

stdin JSON (всё опционально):
  collectors: ["google","zakupki","hh","frp","regional","vk","browser"]
  queries|industries+regions, days, max_items,
  zakupki_keywords, hh_queries, hh_area, feeds:[{name,url}],
  vk_token, vk_keywords, browser_urls, browser_solve,
  dadata_token, enrich(bool), enrich_max, pace_min, pace_max
stdout JSON: {events:[...], summary:{...}}"""
import os, sys, json, re, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_company as VC  # _provider_call_stdlib, _fetch (обход Turnstile)
try:
    import enrich_contacts as EC  # сайт->контакты (роль-email)
except Exception:  # noqa: BLE001
    EC = None
try:
    import browser_probe as BP  # рендер+капча для гиперлокала (Playwright, только сервер)
except Exception:  # noqa: BLE001
    BP = None

# капекс-предфильтр для firehose-лент (заголовок должен намекать на стройку/ввод/инвестиции)
_CAPEX_KW = re.compile(
    r'завод|цех[ауе]?\b|цех$|производств|предприят|комбинат|фабрик|элеватор|'
    r'запуск|запуст|ввод|введ|открыл|строит|стройк|возвед|модерниз|расшир|реконструкц|'
    r'инвест|вложит|вложен|млрд|мощност|линия|линию|перерабо|логистическ|'
    r'ФРП|ОЭЗ|ТОР\b|ТОСЭР|индустриальн|технопарк|резидент|импортозамещ', re.I)
TRIGGERS = ['строительство завода', 'запуск цеха', 'новый цех', 'модернизация производства',
            'расширение производства', 'ввод мощностей', 'запуск линии', 'инвестиции в производство',
            'займ ФРП', 'резидент индустриального парка', 'новое производство']
# ICP = РЕАЛЬНАЯ обзвон-база (правило владельца: «всё что в базе = наш ОКВЭД»). Набор
# из 39 разделов, фактически присутствующих в obzvon_all (161762 юрлица).
ICP_OKVED = frozenset(('01', '03', '06', '07', '08', '09', '10', '11', '19', '20', '21',
                       '22', '23', '24', '25', '27', '28', '35', '36', '37', '38', '41',
                       '42', '43', '46', '49', '52', '59', '62', '68', '71', '72', '77',
                       '78', '82', '84', '85', '86', '93'))
# Тегирование направления по ОКВЭД (какой продукт питчить). КЦ = компрессоры/генераторы
# азота-кислорода (нужны почти всем производствам). Meyer = фотосепараторы/рентген-инспекция
# (зерно/пищёвка/вторсырьё/руда/логистика). Пересечение (напр. пищёвка 10,11) = оба.
KC_OKVED = frozenset(('01', '03', '06', '09', '10', '11', '19', '20', '21', '22', '23',
                      '24', '25', '27', '28', '35', '36', '86'))
MEYER_OKVED = frozenset(('01', '03', '07', '08', '10', '11', '21', '22', '38', '46', '49', '52', '84'))


def division_of(okved):
    """Направление(я) по ОКВЭД: 'kc' | 'meyer' | 'kc+meyer'. Дефолт kc (сжатый воздух
    нужен почти везде), meyer добавляется для профильных отраслей."""
    p = str(okved or '').replace('.', '')[:2]
    divs = []
    if p in KC_OKVED or (p not in MEYER_OKVED):
        divs.append('kc')
    if p in MEYER_OKVED:
        divs.append('meyer')
    return '+'.join(divs) if divs else 'kc'


KC_INDUSTRIES = ('металлообработка', 'пищевое производство', 'химический завод',
                 'фармацевтический завод', 'нефтепереработка', 'газопереработка',
                 'металлургический комбинат', 'стекольный завод', 'цементный завод',
                 'деревообработка', 'упаковочное производство', 'водоочистная станция',
                 'лазерная резка', 'шинный завод', 'аквакультура', 'промышленный парк',
                 'машиностроительный завод', 'больница', 'горно-обогатительный комбинат')
MEYER_INDUSTRIES = ('зернопереработка', 'элеватор', 'мукомольный комбинат', 'крупяной завод',
                    'семеноводство', 'переработка орехов', 'сортировка вторсырья',
                    'переработка пластика', 'обогатительная фабрика', 'консервный завод',
                    'мясоперерабатывающий завод', 'агропромышленный комплекс', 'кофейное производство')
# слова расширения в вакансиях (Тир-5): всплеск = стройка/новая линия
HH_SIGNALS = ['наладчик станков с ЧПУ', 'оператор станков с ЧПУ', 'главный энергетик',
              'начальник производства', 'инженер-механик компрессорного', 'главный инженер завод']
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'


# --------------------------------------------------------------- утилиты
# ВАЖНО (диагностировано на сервере 2026-07-21): системный SOCKS-прокси сервера РЕЖЕТ многие
# хосты («Connection not allowed»), а госсайты (zakupki и пр.) отдают Russian-Trusted-CA
# сертификат → обычный urlopen падает CERTIFICATE_VERIFY_FAILED. Обходим как в enrich (_DIRECT):
# опенер с ПУСТЫМ ProxyHandler (в обход системного прокси) + неверифицирующий TLS-контекст.
# Медиа-RSS при этом достижимы (lenta отдаёт 200 items), но при заливе залпом дают
# RemoteDisconnected — поэтому лёгкий ретрай + пейсинг.
import ssl as _ssl
_SSLCTX = _ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = _ssl.CERT_NONE
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=_SSLCTX))


def _get(url, timeout=25, headers=None, tries=3):
    h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Language': 'ru,en;q=0.8'}
    if headers:
        h.update(headers)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            return _NOPROXY.open(req, timeout=timeout).read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            if i < tries - 1:
                time.sleep(1.0 * (i + 1) + _rnd.uniform(0, 0.8))
    return ''


# --- ротация мобильных IP (PROXY_URLV2 asocks-пул) для фетча RSS: каждый запрос с нового
# IP → Google News не режет по IP (при одном IP + 10 потоках он отдаёт пусто). ---
import random as _rnd

_OPENERS = None


def _build_openers():
    """Собрать по опенеру на каждый прокси из пула VC (мобильные socks5/http)."""
    ops = []
    try:
        import verify_company as VC
        pool = list(getattr(VC, 'PROXY_POOL', []) or [])
    except Exception:  # noqa: BLE001
        pool = []
    for u in pool[:30]:
        try:
            p = urllib.parse.urlsplit(u if '://' in u else 'http://' + u)
            if p.scheme.startswith('socks'):
                import socks  # PySocks
                from sockshandler import SocksiPyHandler
                ops.append(urllib.request.build_opener(SocksiPyHandler(
                    socks.SOCKS5, p.hostname, p.port or 1080,
                    username=p.username, password=p.password, rdns=True)))
            else:
                ops.append(urllib.request.build_opener(
                    urllib.request.ProxyHandler({'http': u, 'https': u})))
        except Exception:  # noqa: BLE001
            continue
    return ops


def _proxied_get(url, timeout=20, headers=None):
    """РАНЬШЕ: ротация мобильных IP для Google News. Google News на сервере DPI-заблокирован
    (SSL EOF и напрямую, и через все прокси), а прямой bypass-фетч _get достаёт РФ-медиа/гос.
    Поэтому просто идём через _get (bypass системного прокси + неверифицирующий TLS + ретрай)."""
    return _get(url, timeout, headers)


def fresh(pubdate, days):
    try:
        dt = parsedate_to_datetime(pubdate)
        return (time.time() - dt.timestamp()) <= days * 86400
    except Exception:  # noqa: BLE001
        return True


def _rss_items(body):
    """Разобрать RSS/Atom -> [{title,link,pubDate,source}]."""
    out = []
    for it in re.findall(r'<item>(.*?)</item>', body, re.S) or \
              re.findall(r'<entry>(.*?)</entry>', body, re.S):
        def g(tag):
            m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', it, re.S)
            return re.sub(r'<!\[CDATA\[|\]\]>', '', m.group(1)).strip() if m else ''
        link = g('link')
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', it)
            link = m.group(1) if m else ''
        out.append({'title': re.sub(r'<[^>]+>', ' ', g('title')).strip(),
                    'link': link, 'pubDate': g('pubDate') or g('published') or g('updated'),
                    'source': g('source')})
    return out


# --------------------------------------------------------------- коллекторы
def col_google(queries, days, max_items):
    """Тир-4: Google News RSS по запросам-триггерам. ПАРАЛЛЕЛЬНО (10 потоков,
    таймаут 15с) — последовательный обход 80+ запросов упирался в 30-мин лимит
    задания раннера."""
    def one(q):
        url = ('https://news.google.com/rss/search?q=' + urllib.parse.quote(q)
               + '&hl=ru&gl=RU&ceid=RU:ru')
        time.sleep(_rnd.uniform(0.3, 1.5))  # джиттер — не долбить залпом
        return q, _rss_items(_proxied_get(url, timeout=18))  # ротация мобильных IP
    items = []
    with ThreadPoolExecutor(max_workers=5) as ex:  # меньше потоков: Google режет залп
        results = list(ex.map(lambda q: one(q), queries))
    for q, its in results:
        for it in its[:max_items]:
            if it['title'] and fresh(it['pubDate'], days):
                it.update({'tier': 4, 'collector': 'google', 'query': q})
                items.append(it)
    return items


def col_regional(feeds, days, max_items):
    """Тир-1/4: региональные/райгазетные/отраслевые RSS из каталога (news-sources.json /
    args.feeds). ПАРАЛЛЕЛЬНО (6 потоков + джиттер): каталог вырос до 100+ фидов (85 регионов
    + отрасли), последовательный обход упирался в 30-мин лимит задания."""
    def one(f):
        url = f.get('url') if isinstance(f, dict) else f
        name = f.get('name') if isinstance(f, dict) else ''
        if not url:
            return []
        time.sleep(_rnd.uniform(0.3, 1.5))  # джиттер — Google режет залп
        try:
            body = _proxied_get(url, timeout=18) if 'news.google.com' in url else _get(url)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for it in _rss_items(body)[:max_items]:
            if it['title'] and fresh(it['pubDate'], days):
                it.update({'tier': f.get('tier', 1) if isinstance(f, dict) else 1,
                           'collector': 'regional', 'source': name or it.get('source')})
                out.append(it)
        return out
    items = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for out in ex.map(one, feeds or []):
            items.extend(out)
    return items


def col_zakupki(keywords, days, max_items):
    """Тир-3: zakupki.gov.ru EIS RSS по ключам (компрессоры/стройка цеха)."""
    items = []
    for kw in keywords:
        url = ('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
               + urllib.parse.quote(kw) + '&morphology=on&sortBy=UPDATE_DATE'
               + '&recordsPerPage=_10&fz44=on&fz223=on&af=on')
        for it in _rss_items(_get(url, headers={'Accept': 'application/rss+xml'}))[:max_items]:
            if it['title']:
                it.update({'tier': 3, 'collector': 'zakupki',
                           'source': 'zakupki.gov.ru', 'query': kw})
                items.append(it)
    return items


def col_hh(queries, area, days, max_items):
    """Тир-5: hh.ru API — свежие вакансии-сигналы расширения (наладчик ЧПУ и т.п.)."""
    items = []
    period = min(int(days), 30)  # hh отдаёт максимум 30 дней
    for q in queries:
        url = ('https://api.hh.ru/vacancies?text=' + urllib.parse.quote('"%s"' % q)
               + f'&per_page={max_items}&order_by=publication_time&period={period}'
               + (f'&area={area}' if area else ''))
        try:
            d = json.loads(_get(url, headers={'Accept': 'application/json'}) or '{}')
        except Exception:  # noqa: BLE001
            d = {}
        for v in (d.get('items') or [])[:max_items]:
            emp = (v.get('employer') or {}).get('name') or ''
            reg = (v.get('area') or {}).get('name') or ''
            if not emp:
                continue
            items.append({'title': f'{emp} ищет «{q}» ({reg}) — сигнал расширения производства',
                          'link': v.get('alternate_url') or '', 'pubDate': v.get('published_at') or '',
                          'source': 'hh.ru', 'tier': 5, 'collector': 'hh',
                          'company_hint': emp, 'query': q})
    return items


def col_frp(days, max_items):
    """Тир-2: ФРП (frprf.ru) — новости о займах/проектах (капекс подтверждён). Через VC._fetch
    (обход Turnstile при необходимости)."""
    items = []
    for path in ('https://frprf.ru/press-tsentr/novosti/', 'https://frprf.ru/press-tsentr/novosti/'):
        html, method, meta = (VC._fetch(path) if hasattr(VC, '_fetch') else (_get(path), 'direct', {}))
        if not html or (isinstance(meta, dict) and meta.get('captcha_type')):
            continue
        for m in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href, txt = m[0], re.sub(r'<[^>]+>', ' ', m[1]).strip()
            if len(txt) > 25 and any(w in txt.lower() for w in
                                     ('завод', 'цех', 'производств', 'линию', 'займ', 'проект', 'млн', 'млрд')):
                link = href if href.startswith('http') else 'https://frprf.ru' + href
                items.append({'title': txt[:200], 'link': link, 'pubDate': '',
                              'source': 'ФРП', 'tier': 2, 'collector': 'frp'})
            if len(items) >= max_items:
                break
        if items:
            break
    return items


def col_vk(keywords, token, days, max_items):
    """Тир-1: ВК newsfeed.search по ключам (районные паблики). Нужен vk_token."""
    if not token:
        return []
    items = []
    for kw in keywords:
        url = ('https://api.vk.com/method/newsfeed.search?q=' + urllib.parse.quote(kw)
               + f'&count={max_items}&access_token={token}&v=5.199')
        try:
            d = json.loads(_get(url) or '{}')
        except Exception:  # noqa: BLE001
            d = {}
        for p in ((d.get('response') or {}).get('items') or [])[:max_items]:
            txt = (p.get('text') or '').strip()
            if not txt or not fresh_ts(p.get('date'), days):
                continue
            oid, pid = p.get('owner_id'), p.get('id')
            items.append({'title': txt[:200], 'link': f'https://vk.com/wall{oid}_{pid}',
                          'pubDate': '', 'source': 'ВКонтакте', 'tier': 1,
                          'collector': 'vk', 'query': kw})
    return items


def fresh_ts(ts, days):
    try:
        return (time.time() - int(ts)) <= days * 86400
    except Exception:  # noqa: BLE001
        return True


def col_browser(urls, solve):
    """Тир-1: гиперлокал за капчей (ОК/райсайты) через browser_probe (Playwright+CapMonster).
    Пока — по КОНКРЕТНЫМ URL статей (листинги пабликов требуют возврата полного HTML,
    добавим отдельно). Возвращает заголовок+сниппет как item для провайдера."""
    if BP is None:
        return []
    items = []
    for u in urls or []:
        try:
            r = BP.probe({'url': u, 'solve': bool(solve), 'screenshot': False, 'wait_ms': 5000})
        except Exception as e:  # noqa: BLE001
            r = {'error': str(e)[:80]}
        title = (r.get('title') or '') + '. ' + (r.get('text_snippet') or '')
        if title.strip('. '):
            items.append({'title': title[:300], 'link': u, 'pubDate': '',
                          'source': r.get('title') or 'гиперлокал', 'tier': 1,
                          'collector': 'browser', 'captcha_type': r.get('captcha_type')})
    return items


# --------------------------------------------------------------- извлечение
def extract_event(title, source):
    prompt = (
        'Из текста новости/сигнала определи, есть ли КАПЕКС-событие компании (стройка/'
        'модернизация/запуск цеха-линии/расширение/инвестиции/займ ФРП/резидентство/'
        'всплеск найма под расширение), после которого компании скоро нужно промышленное '
        'оборудование Руспрома — ЛИБО компрессоры/генераторы азота-кислорода (любое '
        'производство/стройка/добыча), ЛИБО фотосепараторы/рентген-инспекция (зерно, '
        'пищёвка, переработка, сортировка вторсырья/руды, логистика). Верни СТРОГО JSON без markdown: '
        '{"is_capex":true/false,"company":"название компании или пусто",'
        '"event_type":"новый завод|модернизация|запуск линии|расширение|инвестиции|тендер|найм|прочее",'
        '"what":"что строят/делают кратко","region":"регион/город или пусто",'
        '"country":"РФ если в России, иначе страна",'
        '"sum":"сумма инвестиций если есть","hotness":1-5}. '
        f'Текст: "{title}" (источник: {source}).')
    try:
        out = VC._provider_call_stdlib(prompt)
        m = re.search(r'\{.*\}', out or '', re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None


def dadata_suggest(name, token):
    if not name or not token:
        return None
    try:
        body = json.dumps({'query': name, 'count': 1}).encode()
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
            data=body, method='POST', headers={'Content-Type': 'application/json',
            'Accept': 'application/json', 'Authorization': f'Token {token}'})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        s = (d.get('suggestions') or [])
        if not s:
            return None
        data = s[0].get('data', {})
        return {'inn': data.get('inn'), 'okved': data.get('okved') or '',
                'name': s[0].get('value'),
                'region': ((data.get('address') or {}).get('data') or {}).get('region'),
                'status': (data.get('state') or {}).get('status')}
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------- main
def collect_all(args):
    days = int(args.get('days', 90))
    max_items = int(args.get('max_items', 6))
    enabled = args.get('collectors') or ['google', 'zakupki', 'hh', 'frp']
    queries = args.get('queries')
    if not queries:
        # оба направления: КЦ (компрессоры/газогенераторы) + Meyer (фотосепараторы/рентген)
        inds = args.get('industries') or list(KC_INDUSTRIES) + list(MEYER_INDUSTRIES)
        regs = args.get('regions', [''])
        queries = [f'{t} {ind} {reg}'.strip() for t in TRIGGERS[:6] for ind in inds for reg in regs]

    raw = []
    if 'google' in enabled:
        raw += col_google(queries, days, max_items)
    if 'regional' in enabled:
        feeds = args.get('feeds') or _load_feeds_catalog()
        raw += col_regional(feeds, days, max_items)
    if 'zakupki' in enabled:
        kw = args.get('zakupki_keywords') or [
            'компрессорная установка', 'компрессор винтовой', 'генератор азота',
            'генератор кислорода', 'осушитель сжатого воздуха',
            'фотосепаратор', 'оптический сортировщик', 'рентген инспекция',
            'строительство производственного корпуса']
        raw += col_zakupki(kw, days, max_items)
    if 'hh' in enabled:
        raw += col_hh(args.get('hh_queries') or HH_SIGNALS, args.get('hh_area', '113'), days, max_items)
    if 'frp' in enabled:
        raw += col_frp(days, max_items * 3)
    if 'vk' in enabled:
        raw += col_vk(args.get('vk_keywords') or ['построили новый цех', 'открыли производство',
                      'запустили линию'], args.get('vk_token') or os.environ.get('VK_TOKEN', ''),
                      days, max_items)
    if 'browser' in enabled:
        raw += col_browser(args.get('browser_urls'), args.get('browser_solve', True))

    # дедуп по заголовку и ссылке
    seen, dedup = set(), []
    for it in raw:
        k = (it.get('title', '')[:70], it.get('link', ''))
        if k in seen or not it.get('title'):
            continue
        seen.add(k)
        dedup.append(it)
    # КАПЕКС-ПРЕДФИЛЬТР: медиа-ленты (regional/google) — это firehose (lenta/ТАСС/Ъ отдают
    # 200-490 items общих новостей). Прогонять всё через провайдера дорого и шумно — сначала
    # грубый фильтр по капекс-ключам в заголовке. zakupki/hh/frp уже таргетированы — их пропускаем.
    kept = []
    for it in dedup:
        if it.get('collector') in ('regional', 'google'):
            if not _CAPEX_KW.search(it.get('title', '')):
                continue
        kept.append(it)
    return kept


def _load_feeds_catalog():
    """Каталог региональных/гиперлокал RSS с дропа (news-sources.json), если есть."""
    try:
        url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/news-sources.json'
        req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        return json.loads(urllib.request.urlopen(req, timeout=30).read()).get('feeds', [])
    except Exception:  # noqa: BLE001
        return []


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    # ДИАГНОСТИКА фетча RSS: что реально видит сервер (прямой vs прокси), сколько item'ов
    # проба xmlriver-Google: их серверы делают запрос → DPI-блок нашего сервера не мешает.
    # Проверяем обычный Google-поиск, вертикаль новостей (tbm=nws) и свежесть (qdr:d).
    if args.get('xmlriver_probe'):
        user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
        if not (user and key):
            json.dump({'error': 'нет XMLRIVER_USER/KEY в env'}, sys.stdout, ensure_ascii=False)
            return
        q = args.get('q', '"запуск производства" завод')
        base = ('http://xmlriver.com/search/xml?user=' + urllib.parse.quote(user)
                + '&key=' + urllib.parse.quote(key) + '&query=' + urllib.parse.quote(q))
        variants = {
            'google-обычный': base,
            'google-новости-tbm': base + '&tbm=nws',
            'google-за-день': base + '&tbs=qdr:d',
            'google-новости-за-день': base + '&tbm=nws&tbs=qdr:d',
        }
        out = {}
        for name, u in variants.items():
            try:
                body = _NOPROXY.open(urllib.request.Request(u, headers={'User-Agent': UA}),
                                     timeout=40).read().decode('utf-8', 'replace')
                titles = re.findall(r'<title>(.*?)</title>', body)[:5]
                err = re.search(r'<error[^>]*>(.*?)</error>', body)
                out[name] = {'len': len(body), 'n_results': len(re.findall(r'<url>', body)),
                             'error': err.group(1)[:80] if err else None,
                             'titles': [re.sub(r'<[^>]+>', '', t)[:70] for t in titles]}
            except Exception as e:  # noqa: BLE001
                out[name] = {'error': type(e).__name__ + ':' + str(e)[:80]}
        json.dump({'q': q, 'probe': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('probe_url') or args.get('probe_urls'):
        urls = args.get('probe_urls') or [args['probe_url']]
        _NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def raw_direct(u, bypass=False):
            try:
                req = urllib.request.Request(u, headers={'User-Agent': UA})
                if bypass:
                    r = _NOPROXY.open(req, timeout=20)
                else:
                    r = urllib.request.urlopen(req, timeout=20)
                b = r.read().decode('utf-8', 'replace')
                return {'status': getattr(r, 'status', r.getcode()), 'len': len(b),
                        'items': len(_rss_items(b)), 'head': b[:150]}
            except Exception as e:  # noqa: BLE001
                return {'error': type(e).__name__ + ':' + str(e)[:120]}
        def raw_proxy(u):
            ops = _build_openers()
            if not ops:
                return {'error': 'no-openers'}
            res = []
            for op in ops[:3]:
                try:
                    req = urllib.request.Request(u, headers={'User-Agent': UA})
                    b = op.open(req, timeout=20).read().decode('utf-8', 'replace')
                    res.append({'len': len(b), 'items': len(_rss_items(b))})
                except Exception as e:  # noqa: BLE001
                    res.append({'error': type(e).__name__ + ':' + str(e)[:80]})
            return {'n_openers': len(ops), 'tries': res}
        def via_get(u):
            b = _get(u, timeout=20)
            return {'len': len(b), 'items': len(_rss_items(b)), 'head': b[:80]}
        out = []
        for u in urls:
            rec = {'url': u[:90], 'get': via_get(u)}
            if args.get('probe_raw'):
                rec['direct'] = raw_direct(u)
                rec['bypass'] = raw_direct(u, bypass=True)
            out.append(rec)
        json.dump({'probe': out}, sys.stdout, ensure_ascii=False)
        return
    token = args.get('dadata_token') or os.environ.get('DADATA_TOKEN', '')
    enrich = bool(args.get('enrich'))
    enrich_max = int(args.get('enrich_max', 15))
    pace = (float(args.get('pace_min', 6.0)), float(args.get('pace_max', 14.0)))

    raw = collect_all(args)

    def enrich_ev(it):
        ev = extract_event(it['title'], it.get('source', ''))
        if not ev or not ev.get('is_capex'):
            return None
        # только РФ (в новостях мелькают Казахстан/Беларусь — их не берём)
        ctry = str(ev.get('country', '')).lower()
        if ctry and not any(w in ctry for w in ('рф', 'росс', 'russia')):
            return None
        rec = {'title': it['title'], 'source_url': it['link'],  # ССЫЛКА — обязательна
               'source_name': it.get('source', ''), 'published': it.get('pubDate', ''),
               'tier': it.get('tier'), 'collector': it.get('collector'),
               'event_type': ev.get('event_type'), 'what': ev.get('what'),
               'region': ev.get('region'), 'sum': ev.get('sum'),
               'hotness': ev.get('hotness'), 'country': ev.get('country'),
               'company': ev.get('company') or it.get('company_hint'), 'is_capex': True}
        dd = dadata_suggest(rec['company'], token)
        if dd:
            rec.update({'inn': dd['inn'], 'okved': dd['okved'],
                        'company_full': dd['name'], 'status': dd['status'],
                        'dd_region': dd['region']})
            rec['icp_fit'] = str(dd['okved']).replace('.', '')[:2] in ICP_OKVED
            rec['division'] = division_of(dd['okved'])   # kc | meyer | kc+meyer
        else:
            rec['icp_fit'] = None
            rec['division'] = None
        return rec

    with ThreadPoolExecutor(max_workers=8) as ex:
        events = [e for e in ex.map(enrich_ev, raw) if e]
    events.sort(key=lambda e: (e.get('icp_fit') is True, e.get('hotness') or 0,
                               -(e.get('tier') or 9)), reverse=True)

    # инлайн-обогащение контактов (СЕРВЕР: сайт->роль-email, РФ-IP + обход Turnstile)
    enriched_n = 0
    if enrich and EC is not None:
        cands = [e for e in events if e.get('company') and
                 (e.get('icp_fit') is not False)][:enrich_max]
        for e in cands:
            comp = {'inn': e.get('inn'), 'name': e.get('company'),
                    'city': e.get('region') or e.get('dd_region') or ''}
            try:
                c = EC.enrich_one(comp, pace)
                e['contacts'] = {'site': c.get('site'), 'emails': c.get('emails', []),
                                 'best_for_outreach': c.get('best_for_outreach'),
                                 'phones': c.get('phones', []), 'error': c.get('error')}
                if c.get('best_for_outreach') or c.get('emails'):
                    enriched_n += 1
            except Exception as ex2:  # noqa: BLE001
                e['contacts'] = {'error': f'enrich-exc:{str(ex2)[:80]}'}

    # запись лидов в единое хранилище enrich.db (по ИНН): компания + сигнал-новость + email
    saved = 0
    if args.get('write_db', True):
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
            for e in events:
                inn = str(e.get('inn') or '')
                if not inn:
                    continue
                db.upsert_company(inn, name=e.get('company_full') or e.get('company'),
                                  division=e.get('division'), okved=e.get('okved'),
                                  region=e.get('dd_region') or e.get('region'),
                                  site=(e.get('contacts') or {}).get('site'),
                                  best_email=(e.get('contacts') or {}).get('best_for_outreach'))
                db.add_signal(inn, source=e.get('source_name') or e.get('collector') or 'news',
                              event_type=e.get('event_type') or '', what=e.get('what') or '',
                              sum=str(e.get('sum') or ''), source_url=e.get('source_url') or '',
                              hotness=int(e.get('hotness') or 0), ts=e.get('published') or '')
                for em in ((e.get('contacts') or {}).get('emails') or []):
                    if em.get('email'):
                        db.add_email(inn, em.get('email', ''), role=em.get('role', ''),
                                     person=em.get('person', ''), source='news')
                saved += 1
        except Exception as ex3:  # noqa: BLE001
            sys.stderr.write(f'enrich_db write skip: {str(ex3)[:120]}\n')

    json.dump({'events': events, 'count': len(events),
               'summary': {'collectors': args.get('collectors') or ['google', 'zakupki', 'hh', 'frp'],
                           'proxy_openers': len(_OPENERS or []),
                           'raw_items': len(raw), 'capex_events': len(events),
                           'icp_fit': sum(1 for e in events if e.get('icp_fit')),
                           'with_inn': sum(1 for e in events if e.get('inn')),
                           'saved_to_db': saved,
                           'enriched_contacts': enriched_n,
                           'by_tier': dict(Counter(e.get('tier') for e in events)),
                           'by_collector': dict(Counter(e.get('collector') for e in events)),
                           'by_type': dict(Counter(e.get('event_type') for e in events))}},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
