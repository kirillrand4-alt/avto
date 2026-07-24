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
import os, sys, json, re, time, threading
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


def _chain_sweep(args, next_offset):
    """Самочейнинг news-sweep: пишем СЛЕДУЮЩИЙ подписанный job (offset=next_offset) на дроп.
    Как в mass-обогащении — прогон живёт на сервере, переживает таймаут/рестарт песочницы.
    Стоп: флаг sweep_stop.flag на дропе, либо offset>=len(каталога)."""
    import hmac as _h, hashlib as _hl
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    sec = os.environ.get('JOB_SECRET', '')
    if not (drop and tok):
        return 'no-drop-env'
    _D = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # прямой (обход сис-прокси)
    try:
        req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tok})
        if any(f.get('name') == 'sweep_stop.flag' for f in json.loads(_D.open(req, timeout=30).read())):
            return 'stopped-by-flag'
    except Exception:  # noqa: BLE001
        pass
    a = dict(args)
    a['offset'] = next_offset
    jid = f'{int(time.time())}-sweep{os.getpid()}'
    job = {'id': jid, 'task': 'news_scan', 'args': a, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'], 'ts': job['ts']},
                       sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    if sec:
        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
    # РЕТРАЙ записи преемника: единственный PUT без ретрая = один транзиент рвал ВСЮ цепочку
    # навсегда (дроп забит тысячами файлов → list/PUT флапают). 4 попытки с backoff.
    last = ''
    for _att in range(4):
        try:
            _D.open(urllib.request.Request(
                drop + f'/job-{jid}.json', data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                method='PUT', headers={'X-Drop-Token': tok}), timeout=60)
            return jid
        except Exception as e:  # noqa: BLE001
            last = str(e)[:60]
            time.sleep(2 * (_att + 1))
    return f'chain-err:{last}'


def _load_sweep_catalog():
    """Каталог sweep-запросов. ЛОКАЛЬНЫЙ КЭШ (грузим с дропа один раз, дальше с диска):
    раньше был один urlopen через СИСТЕМНЫЙ прокси сервера без ретрая — он периодически
    флапал → пустой каталог → 0 запросов в чанке И пустой qs → цепочка НЕ писала преемника
    (главная причина затыка sweep на одном offset). Теперь: кэш → прямой опенер (обход
    прокси) с ретраем → при успехе сохраняем на диск. Каталог фиксированный, кэш безопасен
    (для обновления — удалить .sweep_catalog.json)."""
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sweep_catalog.json')
    if os.path.exists(local):
        try:
            d = json.load(open(local, encoding='utf-8'))
            if d:
                return d
        except Exception:  # noqa: BLE001
            pass
    url = os.environ.get('DROP_URL', '').rstrip('/') + '/sweep_queries.json'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # без системного прокси
    for _att in range(4):
        try:
            req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
            d = json.loads(opener.open(req, timeout=60).read())
            if d:
                try:
                    json.dump(d, open(local, 'w', encoding='utf-8'), ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    pass
                return d
        except Exception:  # noqa: BLE001
            time.sleep(2 * (_att + 1))
    return []


# капекс-термы для VK-свипа (гоняются × локация, без кавычек). ШИРОКИЕ термы — A/B показал, что
# они дают БОЛЬШЕ событий, чем точные фразы (raw больше, капекс-гейт+fable вычищают мусор). VK НЕ
# держит OR-блок (проверено: raw=2) → только отдельные термы. Голые глаголы не берём (утонет в шуме).
_VK_PHRASES = [   # 10 штук (владелец: вдвое меньше запросов). Семантическая дедупликация 20:
    # «завод×5» и «производство×5» почти-дубли по выдаче — оставлен 1 представитель ветки.
    'новый завод', 'строительство завода', 'запуск производства', 'новый цех',
    'модернизация производства', 'расширение производства', 'ввод в эксплуатацию',
    'запустили линию', 'инвестпроект', 'резидент ОЭЗ',
]


def _load_vk_localities():
    """Каталог локаций для VK-свипа (8.5к городов из sweep-каталога, крупные-первыми).
    Как _load_sweep_catalog: локальный кэш → прямой опенер (обход сис-прокси) → ретрай.
    Обновление — удалить .vk_localities.json."""
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.vk_localities.json')
    if os.path.exists(local):
        try:
            d = json.load(open(local, encoding='utf-8'))
            if d:
                return d
        except Exception:  # noqa: BLE001
            pass
    url = os.environ.get('DROP_URL', '').rstrip('/') + '/vk_localities.json'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _att in range(4):
        try:
            req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
            d = json.loads(opener.open(req, timeout=60).read())
            if d:
                try:
                    json.dump(d, open(local, 'w', encoding='utf-8'), ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    pass
                return d
        except Exception:  # noqa: BLE001
            time.sleep(2 * (_att + 1))
    return []


def _chain_vk_sweep(args, next_offset):
    """Самочейнинг VK-свипа: пишем СЛЕДУЮЩИЙ подписанный vk_sweep-job на дроп. Джоб ЛЁГКИЙ
    (нет sweep/xmlriver_queries → _is_heavy=False) → идёт ПАРАЛЛЕЛЬНО xmlriver-свипу.
    Стоп: vk_sweep_stop.flag на дропе, либо offset>=len(локаций)."""
    import hmac as _h, hashlib as _hl
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    sec = os.environ.get('JOB_SECRET', '')
    if not (drop and tok):
        return 'no-drop-env'
    _D = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # ИДЕМПОТЕНТНОСТЬ (инцидент 2026-07-23: рестарт раннера переисполнял джоб с дропа, каждый
    # постил преемника → 57 дублей одной цепочки, дравшихся за единый VK-токен). Перед постингом
    # преемника: (а) стоп-флаг; (б) если vksweep-джоб УЖЕ в очереди — не плодим копию (одна цепочка).
    try:
        req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tok})
        names = [f.get('name', '') for f in json.loads(_D.open(req, timeout=30).read())]
        if any(n == 'vk_sweep_stop.flag' for n in names):
            return 'stopped-by-flag'
        # текущий джоб ещё НА дропе (раннер удалит его ПОСЛЕ) → он сам в списке. Копия цепочки =
        # когда vksweep-джобов ≥2 (сам + чужой): тогда не постим преемника. По мере слива форков
        # последний увидит ровно 1 (себя) и продолжит → сходимся к одной цепочке без ручного вмешательства.
        vk_jobs = sum(1 for n in names if n.startswith('job-') and 'vksweep' in n)
        if vk_jobs >= 2:
            return 'skip-dup-chain-live'
    except Exception:  # noqa: BLE001
        pass
    a = dict(args)
    a['offset'] = next_offset
    a.pop('vk_queries_built', None)   # не тащим раздутый список запросов в подпись/джоб
    a.pop('_vk_next', None)           # транзиент; преемник посчитает свой
    jid = f'{int(time.time())}-vksweep{os.getpid()}'
    job = {'id': jid, 'task': 'news_scan', 'args': a, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'], 'ts': job['ts']},
                       sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    if sec:
        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
    last = ''
    for _att in range(4):
        try:
            _D.open(urllib.request.Request(
                drop + f'/job-{jid}.json', data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                method='PUT', headers={'X-Drop-Token': tok}), timeout=60)
            return jid
        except Exception as e:  # noqa: BLE001
            last = str(e)[:60]
            time.sleep(2 * (_att + 1))
    return f'vkchain-err:{last}'


def _norm_url(u):
    """Каноничный URL для дедупа: без схемы/www/якоря/трекинг-параметров/хвостового слэша.
    Одна статья из Google и Яндекса (разные трекинг-хвосты) → один ключ."""
    u = (u or '').split('#')[0]
    u = re.sub(r'^https?://', '', u).lstrip('www.')
    u = re.sub(r'[?&](utm_[^=&]+|yclid|gclid|from|ref|_openstat)=[^&]*', '', u)
    return u.rstrip('/?&').lower()


def _news_key(it):
    """Ключ дедупа события: канон-URL (точный). Фолбэк — домен+нормализованный заголовок
    (ловит одну статью с разными URL / републикации)."""
    u = _norm_url(it.get('link') or '')
    if u and '/' in u:
        return u
    dom = (re.match(r'([^/]+)', u).group(1) if u else '')
    t = re.sub(r'[^а-яёa-z0-9 ]', '', (it.get('title') or '').lower())[:60]
    return f'{dom}|{t}'


def division_of(okved):
    """Направление(я) по ОКВЭД: 'kc' | 'meyer' | 'kc+meyer'. Сначала ТОЧНЫЙ маппинг владельца
    (77 кодов, файл «ОКВЭД и оборудование», enrich_db.OKVED_DIRECTIONS); если код не в маппинге —
    старый 2-значный фолбэк (дефолт kc: сжатый воздух нужен почти любому производству)."""
    try:
        import enrich_db as _EDB
        d, _b = _EDB.division_for_okveds(okved)
        if d:
            return d
    except Exception:  # noqa: BLE001
        pass
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
# слова расширения в вакансиях (Тир-5): всплеск = стройка/новая линия.
# Компрессорные роли (владелец 2026-07-23: «hh как сигнал ≠ подтверждение — чини»):
# вакансия оператора/машиниста компрессоров = у компании ЕСТЬ/ПОЯВЛЯЕТСЯ компрессорное
# хозяйство — прямой маркер оборудования, не просто «расширение вообще».
HH_SIGNALS = ['наладчик станков с ЧПУ', 'оператор станков с ЧПУ', 'главный энергетик',
              'начальник производства', 'инженер-механик компрессорного', 'главный инженер завод',
              'машинист компрессорных установок', 'оператор компрессорной станции',
              'машинист технологических компрессоров', 'машинист воздуходувных установок',
              'слесарь по ремонту компрессорного оборудования']
# запрос -> тег оборудования (уезжает в сигнал: скоринг/панель видят, ЧТО стоит за наймом)
HH_EQUIPMENT = {'компрессор': 'компрессорное оборудование',
                'воздуходув': 'воздуходувки (аэрация/очистные)',
                'чпу': 'станки ЧПУ (пневматика)',
                'энергетик': 'энергохозяйство'}


def _hh_equipment(q):
    ql = q.lower()
    for k, v in HH_EQUIPMENT.items():
        if k in ql:
            return v
    return ''
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
# РАЗДЕЛЬНЫЕ пулы каналов аккаунта: 10 Google + 10 Яндекс свободно (подтверждено владельцем).
# Гоним двумя пулами параллельно, каждый ≤ своего лимита. main() переставит из args.
_XMLR_G_WORKERS = 3
_XMLR_Y_WORKERS = 3


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


def _gnews_decode(link):
    """news.google.com/rss/articles/CBMi… → конечный URL издателя (декод base64-protobuf).
    Владелец кликнул редирект с битым токеном и попал на ЧУЖУЮ статью — храним конечный URL.
    Не декодируется (обрезан/новый формат) — возвращаем как есть."""
    try:
        m = re.search(r'news\.google\.com/rss/articles/([A-Za-z0-9_\-]+)', link or '')
        if not m:
            return link
        import base64 as _b6
        raw = _b6.urlsafe_b64decode(m.group(1) + '=' * (-len(m.group(1)) % 4))
        urls = re.findall(rb'https?://[\x21-\x7e]+', raw)
        best = ''
        for u in urls:
            try:
                s = u.decode('ascii', 'ignore').rstrip('\x01\x02R')
            except Exception:  # noqa: BLE001
                continue
            if 'google.com' in s:
                continue
            # обрезать хвостовой протобаф-мусор после валидного URL
            s = re.split(r'[\x00-\x1f]', s)[0]
            if len(s) > len(best):
                best = s
        return best or link
    except Exception:  # noqa: BLE001
        return link


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
                    'link': _gnews_decode(link),
                    'pubDate': g('pubDate') or g('published') or g('updated'),
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


def col_xmlriver(queries, days, max_items, engines=('google', 'yandex')):
    """Тир-4: поисковая выдача через xmlriver — ИХ серверы делают запрос → DPI-блок РКН
    нас не касается (идея владельца, проверено пробами). ДВА движка: Google (свежесть
    tbs=qdr) + Яндекс (свежесть оператором date:>; по РФ-регионалке богаче — 13 vs 9 в
    пробе). Транзиент «Выполните перезапрос» — ретраим. Дедуп по title/link в collect_all."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return []
    # свежесть: узкие окна — нативно (qdr/within); широкие (>31д, напр. 90-120) — точный
    # диапазон: Google cdr:1,cd_min..cd_max (MM/DD/YYYY), Яндекс — оператор date:> в запросе.
    import datetime as _dt
    _t = _dt.date.today()
    _from = _t - _dt.timedelta(days=max(1, int(days)))
    wide = days > 31
    qdr = 'd' if days <= 1 else ('w' if days <= 7 else 'm')
    g_tbs = (f'cdr:1,cd_min:{_from.strftime("%m/%d/%Y")},cd_max:{_t.strftime("%m/%d/%Y")}'
             if wide else f'qdr:{qdr}')
    # Яндекс: узкое окно — within (пресеты), широкое (>31д) — оператор date:> БЕЗ within
    # (within=2 режет до 30д и конфликтует с date:>100д → выдача почти пустая, проверено).
    if wide:
        y_within, y_datefilter = '0', f' date:>{_from.strftime("%Y%m%d")}'
    else:
        y_within = '77' if days <= 1 else ('1' if days <= 14 else '2')
        y_datefilter = f' date:>{_from.strftime("%Y%m%d")}' if days > 14 else ''

    def fetch_xml(url):
        body = ''
        for att in range(4):
            body = _get(url, timeout=45)
            if body and 'Выполните перезапрос' not in body and '<error' not in body[:400]:
                break
            time.sleep(2 + att * 2)
        return body

    def _mk(t, u, collector, q):
        dm = re.match(r'https?://([^/]+)', u)
        return {'title': t, 'link': u, 'pubDate': '',
                'source': (dm.group(1) if dm else '').lstrip('www.'),
                'tier': 4, 'collector': collector, 'query': q}

    def parse_docs(body, collector, q):
        out = []
        for doc in re.findall(r'<doc>(.*?)</doc>', body or '', re.S):
            def g(tag, d=doc):
                m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', d, re.S)
                return re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', '', m.group(1)).strip() if m else ''
            t, u = g('title'), g('url')
            if t and u:
                out.append(_mk(t, u, collector, q))
        return out[:max_items]

    def parse_news_block(body, collector, q):
        """<news><item><url>..<title>.. — новостной блок (g_news у Google, y_news у Яндекса)."""
        mnews = re.search(r'<news>(.*?)</news>', body or '', re.S)
        out = []
        for it in re.findall(r'<item>(.*?)</item>', mnews.group(1), re.S) if mnews else []:
            def gi(tag, d=it):
                m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', d, re.S)
                return re.sub(r'<!\[CDATA\[|\]\]>|<[^>]+>', '', m.group(1)).strip() if m else ''
            t, u = gi('title'), gi('url')
            if t and u:
                out.append(_mk(t, u, collector, q))
        return out[:max_items]

    def do_google(q):
        gu = ('http://xmlriver.com/search/xml?user=' + urllib.parse.quote(user)
              + '&key=' + urllib.parse.quote(key) + '&tbs=' + urllib.parse.quote(g_tbs)
              + '&additional=g_news&query=' + urllib.parse.quote(q))
        body = fetch_xml(gu)
        return parse_docs(body, 'xmlriver-google', q) + parse_news_block(body, 'xmlriver-gnews', q)

    def do_yandex(q):
        yu = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
              + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
              + '&additional=y_news&within=' + y_within
              + '&query=' + urllib.parse.quote(q + y_datefilter))
        body = fetch_xml(yu)
        return parse_docs(body, 'xmlriver-yandex', q) + parse_news_block(body, 'xmlriver-ynews', q)

    # аккаунт: 10 каналов Google + 10 Яндекс РАЗДЕЛЬНО → гоним двумя пулами параллельно,
    # каждый ≤ своего лимита (не смешиваем, иначе можно превысить один движок).
    items, qs = [], (queries or [])
    from concurrent.futures import ThreadPoolExecutor as _TPE
    gex = _TPE(max_workers=_XMLR_G_WORKERS) if 'google' in engines else None
    yex = _TPE(max_workers=_XMLR_Y_WORKERS) if 'yandex' in engines else None
    futs = []
    if gex:
        futs += [gex.submit(do_google, q) for q in qs]
    if yex:
        futs += [yex.submit(do_yandex, q) for q in qs]
    for f in futs:
        try:
            items.extend(f.result())
        except Exception:  # noqa: BLE001
            pass
    if gex:
        gex.shutdown(wait=True)
    if yex:
        yex.shutdown(wait=True)
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
        eq = _hh_equipment(q)
        for v in (d.get('items') or [])[:max_items]:
            emp = (v.get('employer') or {}).get('name') or ''
            reg = (v.get('area') or {}).get('name') or ''
            if not emp:
                continue
            # тег оборудования в заголовке -> fable кладёт его в what -> сигнал в панели
            # говорит ЧТО стоит за наймом, а не просто «расширение»
            tag = f' — оборудование: {eq}' if eq else ' — сигнал расширения производства'
            items.append({'title': f'{emp} ищет «{q}» ({reg}){tag}',
                          'link': v.get('alternate_url') or '', 'pubDate': v.get('published_at') or '',
                          'source': 'hh.ru', 'tier': 5, 'collector': 'hh',
                          'company_hint': emp, 'query': q, 'equipment': eq})
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


# мусор в ВК-выдаче (проверено владельцем): личные посты, репосты, реклама, продажи,
# вакансии, мемы. Чистим 4 слоями ДО конвейера (иначе провайдер жжётся на мусор).
_VK_TRASH = re.compile(
    r'продам|продаю|куплю|аренд[ау]|вакансия|требуетс|зарплат|резюме|скидк|акция|распродаж|'
    r'заказать|доставка|подпишись|подписывайтесь|розыгрыш|конкурс|гороскоп|погода|анекдот|'
    r'мем|юмор|знакомств|барахолк|отда[мь] даром', re.I)

# ДАЙДЖЕСТ-посты (владелец 2026-07-24: «АРБАЖ-ИНФО» с подборкой «Время-Вперёд» — не новость):
# сборники из нескольких новостей с «Источник: …» / фед-хэштегами / много маркеров ✍.
# Это агрегатор чужих федеральных новостей, а не событие районной компании.
def _vk_is_digest(txt):
    if txt.count('Источник:') >= 2 or txt.count('✍') >= 2:
        return True
    # max.ru/«наш канал» НЕ маркер (владелец: ссылку на МАХ ставит любой автор);
    # #времявперёд — хэштег конкретного агрегатор-проекта, оставлен
    if re.search(r'#времявперёд|#время_вперёд', txt, re.I):
        return True
    # несколько ЗАГОЛОВКОВ КАПСОМ подряд — типичный дайджест
    if len(re.findall(r'^[А-ЯЁ][А-ЯЁ\s«»\-0-9.,]{25,}$', txt, re.M)) >= 2:
        return True
    return False


_VK_SLEEP = float(os.environ.get('VK_SLEEP', '0.5'))   # пауза между вызовами (RPS-лимит ВК ~3/с)


def col_vk(queries, token, days, max_items, count=100):
    """Тир-1: ВК newsfeed.search (районные паблики, гиперлокал). queries — ГОТОВЫЕ q-строки
    (напр. '"построили новый цех" Магнитогорск' для гео или '"запустили линию"' для нац.).
    Фильтры: только сообщества (owner_id<0), не реклама/репост, обязателен капекс-сигнал,
    минус-словарь мусора. Рейт-лимит: пауза _VK_SLEEP + бэкофф на error 6/29 (too many requests).
    Ссылка поста → link → source_url лида (тот же конвейер, что гугл/яндекс)."""
    if not token:
        return []
    items = []
    for q in queries:
        url = ('https://api.vk.com/method/newsfeed.search?q=' + urllib.parse.quote(q)
               + f'&count={count}&access_token={token}&v=5.199')
        d = {}
        for _try in range(4):
            try:
                d = json.loads(_get(url) or '{}')
            except Exception:  # noqa: BLE001
                d = {}
            if (d.get('error') or {}).get('error_code') in (6, 29):   # rps/дневной лимит
                time.sleep(1.5 * (_try + 1)); continue
            break
        time.sleep(_VK_SLEEP)
        kept = 0
        for p in ((d.get('response') or {}).get('items') or []):
            txt = (p.get('text') or '').strip()
            oid = p.get('owner_id') or 0
            if (not txt or len(txt) < 60 or oid >= 0            # только сообщества, не огрызки
                    or p.get('marked_as_ads') or p.get('copy_history')   # не реклама/репост
                    or not fresh_ts(p.get('date'), days)
                    or not _CAPEX_KW.search(txt)                 # обязателен капекс-сигнал
                    or _VK_TRASH.search(txt)                     # минус-словарь мусора
                    or _vk_is_digest(txt)):                      # дайджест-подборка — не новость
                continue
            pid = p.get('id')
            items.append({'title': txt[:200], 'link': f'https://vk.com/wall{oid}_{pid}',
                          'pubDate': '', 'source': 'ВКонтакте', 'tier': 1,
                          'collector': 'vk', 'query': q})
            kept += 1
            if kept >= max_items:
                break
    return items


def fresh_ts(ts, days):
    try:
        return (time.time() - int(ts)) <= days * 86400
    except Exception:  # noqa: BLE001
        return True


# ---- RSS-доноры: ОПРОС фидов (дискавери уже есть в main: {'rss_discover':'db'} — пишет
# donors.rss durable). col_rss — дешёвый постоянный источник (без xmlriver-квоты),
# тот же конвейер (дедуп/капекс-гейт/fable/БД). Капекс-предфильтр ДО провайдера.
_RSS_TITLE_RE = re.compile(r'<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', re.S | re.I)
_RSS_LINK_TAG_RE = re.compile(r'<link[^>]*>(?:<!\[CDATA\[)?\s*(https?://[^<\s\]]+)', re.I)
_RSS_DATE_RE = re.compile(r'<(?:pubDate|updated|published)[^>]*>([^<]+)<', re.I)


def col_rss(feeds, days, max_items, cap_feeds=60):
    """Тир-2: опрос RSS-фидов доноров. feeds=None → взять из enrich.db (donors.rss!='').
    Капекс-предфильтр по заголовку ДО конвейера (RSS шумный, бережём fable)."""
    if feeds is None:
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
            rows = db.cx.execute(
                "SELECT domain, rss FROM donors WHERE rss!='' AND status='live' "
                'ORDER BY event_count DESC LIMIT ?', (cap_feeds,)).fetchall()
            feeds = [(r[0], r[1]) for r in rows]
        except Exception:  # noqa: BLE001
            return []
    else:
        feeds = [(re.sub(r'https?://([^/]+).*', r'\1', f), f) for f in feeds][:cap_feeds]
    items = []
    for dom, feed in feeds:
        try:
            body = _get(feed) or ''
        except Exception:  # noqa: BLE001
            continue
        kept = 0
        for chunk in re.split(r'<(?:item|entry)[\s>]', body)[1:]:
            t = _RSS_TITLE_RE.search(chunk)
            l = _RSS_LINK_TAG_RE.search(chunk)
            title = re.sub(r'\s+', ' ', (t.group(1) if t else '')).strip()
            link = (l.group(1) if l else '').strip()
            if not title or not link or not _CAPEX_KW.search(title):
                continue
            d = _RSS_DATE_RE.search(chunk)
            items.append({'title': title[:200], 'link': link,
                          'pubDate': (d.group(1).strip() if d else ''),
                          'source': dom, 'tier': 2, 'collector': 'rss', 'query': feed})
            kept += 1
            if kept >= max_items:
                break
        time.sleep(0.4)
    return items


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
        'Из текста новости/сигнала определи, есть ли ПРОМЫШЛЕННОЕ КАПЕКС-событие компании '
        '(стройка/модернизация/запуск цеха-линии/расширение/инвестиции/займ ФРП/резидентство/'
        'всплеск найма под расширение), после которого компании скоро нужно промышленное '
        'оборудование Руспрома — ЛИБО компрессоры/генераторы азота-кислорода (любое '
        'производство/стройка/добыча), ЛИБО фотосепараторы/рентген-инспекция (зерно, '
        'пищёвка, переработка, сортировка вторсырья/руды, логистика). '
        'is_capex=false для: ЖИЛЬЯ и жилых кварталов, дорог/мостов, школ/больниц/соцобъектов, '
        'парков/благоустройства, офисов/ТЦ, а также анонсов БЕЗ конкретной компании-инвестора '
        '(«в регионе планируют», «технопарк откроют») и рекламных/блоговых постов. '
        'Верни СТРОГО JSON без markdown: '
        '{"is_capex":true/false,'
        '"company":"ОФИЦИАЛЬНОЕ название компании В ИМЕНИТЕЛЬНОМ ПАДЕЖЕ (как в ЕГРЮЛ: '
        '«Северсталь», НЕ «Северстали»; без слов завод/компания/предприятие, если они не '
        'часть названия) или пусто",'
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


# слова-контекст/ОПФ, не несущие имени (для вариантов запроса и матч-скоринга)
_OPF_WORDS = {'ооо', 'ао', 'пао', 'зао', 'оао', 'нао', 'ип', 'гуп', 'муп', 'фгуп', 'ано', 'као',
              'завод', 'завода', 'заводе', 'компания', 'компании', 'предприятие', 'предприятия',
              'предприятии', 'группа', 'группы', 'холдинг', 'холдинга', 'гк', 'тд', 'нпо', 'нпп',
              'фирма', 'фирмы', 'корпорация', 'корпорации', 'комбинат', 'комбината', 'фабрика',
              'фабрики'}
# простая расклонка родительного/предложного падежа (суффикс → именительный).
# Порядок важен: длинные суффиксы раньше. Ловит «Северстали»→«Северсталь»,
# «Пикалёвской соды»→«Пикалёвская сода», «Уралмаше»→«Уралмаш».
_DECL_SUF = (('ской', 'ская'), ('цкой', 'цкая'), ('ного', 'ный'), ('ьего', 'ий'),
             ('ого', 'ый'), ('его', 'ий'), ('ии', 'ия'), ('ьи', 'ья'),
             ('ы', 'а'), ('и', 'ь'), ('е', ''), ('у', ''), ('ю', ''))


def _name_variants(name):
    """Варианты имени для dadata-suggest (склонения dadata НЕ понимает — проверено
    эмпирически 2026-07-23: «Северстали»/«Пикалёвской соды» → пусто)."""
    out = [name]
    # ядро в кавычках: «завода "Уралмаш"» -> Уралмаш
    for q in re.findall(r'[«"„]([^»"“]{2,60})[»"“]', name):
        if q not in out:
            out.append(q)
    # без ОПФ/контекст-слов и предлогов (на/в/у/о...)
    toks = re.sub(r'[«»"„“]', ' ', name).split()
    core = [t for t in toks if t.lower().strip('.,') not in _OPF_WORDS
            and not (len(t) <= 2 and t.islower())]
    c = ' '.join(core).strip()
    if c and c not in out:
        out.append(c)
    # расклонка: к каждому слову ≥4 символов применяем первый подходящий суффикс
    def decl(s):
        ws = []
        for w in s.split():
            nw = w
            if len(w) >= 4:
                for suf, rep in _DECL_SUF:
                    if w.lower().endswith(suf):
                        nw = w[:len(w) - len(suf)] + rep
                        break
            ws.append(nw)
        return ' '.join(ws)
    for src in list(out):
        d = decl(src)
        if d and d not in out:
            out.append(d)
    return out[:6]


def _match_score(query_name, sugg_value):
    """Сколько содержательных токенов запроса нашлось в предложении dadata (префикс-сравнение
    по 5 символам — переживает склонение). 0 = не приклеивать ИНН (защита от тёзок)."""
    def toks(s):
        return [t for t in re.sub(r'[^а-яёa-z0-9 ]', ' ', (s or '').lower()).split()
                if len(t) >= 4 and t not in _OPF_WORDS]
    qt, st = toks(query_name), toks(sugg_value)
    n = 0
    for a in qt:
        if any(a[:5] == b[:5] or a.startswith(b[:4]) or b.startswith(a[:4]) for b in st):
            n += 1
            # длинный редкий токен (бренд «северсталь») — надёжнее двух коротких;
            # короткие тёзки («прогресс», 8) буст не получают
            if len(a) >= 9:
                n += 1
    return n


def dadata_suggest(name, token):
    """Название -> ИНН. Варианты (кавычки/без ОПФ/расклонка) × count=3, выбор по матч-скору.
    score=0 -> None (лучше лид без ИНН, чем ЧУЖОЙ ИНН тёзки). confidence: high(≥2)/low(1)."""
    if not name or not token:
        return None
    best = None  # (score, suggestion)
    try:
        for v in _name_variants(name):
            body = json.dumps({'query': v, 'count': 3}).encode()
            req = urllib.request.Request(
                'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                data=body, method='POST', headers={'Content-Type': 'application/json',
                'Accept': 'application/json', 'Authorization': f'Token {token}'})
            # РЕТРАЙ с бэкофф: dadata троттлит IP при заливе (инцидент 2026-07-23: пачка
            # ретраев легла в durable-нерезолв из-за транзиентного 429). Тихий одиночный
            # фейл недопустим.
            d = None
            for _att in range(3):
                try:
                    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
                    break
                except urllib.error.HTTPError as he:
                    if he.code in (429, 500, 502, 503):
                        time.sleep(2.0 * (_att + 1))
                        continue
                    raise
                except Exception:  # noqa: BLE001
                    time.sleep(1.0 * (_att + 1))
            if d is None:
                continue
            for s in (d.get('suggestions') or []):
                sc = _match_score(name, s.get('value') or '')
                if best is None or sc > best[0]:
                    best = (sc, s)
            if best and best[0] >= 2:
                break   # уверенный матч — не жжём лимит dadata
    except Exception:  # noqa: BLE001
        pass
    if not best or best[0] < 1:
        return None
    sc, s = best
    data = s.get('data', {})
    return {'inn': data.get('inn'), 'okved': data.get('okved') or '',
            'name': s.get('value'),
            'region': ((data.get('address') or {}).get('data') or {}).get('region'),
            'status': (data.get('state') or {}).get('status'),
            # email из ЕГРЮЛ (юрзначимые уведомления, с 2025 обязателен) - dadata отдаёт
            # его в этом же ответе, раньше выбрасывали (директива владельца: подключить)
            'egrul_emails': [e.get('value') for e in (data.get('emails') or [])
                             if isinstance(e, dict) and e.get('value')][:3],
            'confidence': 'high' if sc >= 2 else 'low'}


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
    if 'xmlriver' in enabled:
        xq = args.get('xmlriver_queries') or _load_xmlriver_queries()
        raw += col_xmlriver(xq, days, max_items,
                            engines=tuple(args.get('xmlriver_engines') or ('google', 'yandex')))
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
        if args.get('vk_queries_built'):
            vq = args['vk_queries_built']                       # готовые q-строки из vk_sweep
        else:
            vq = [f'"{k}"' for k in (args.get('vk_keywords') or
                  ['построили новый цех', 'открыли производство', 'запустили линию'])]
        raw += col_vk(vq, args.get('vk_token') or os.environ.get('VK_TOKEN', ''),
                      days, max_items, count=int(args.get('vk_count', 100)))
    if 'browser' in enabled:
        raw += col_browser(args.get('browser_urls'), args.get('browser_solve', True))
    if 'rss' in enabled:
        raw += col_rss(args.get('rss_feeds'), days, max_items,
                       cap_feeds=int(args.get('rss_cap_feeds', 60)))

    # дедуп В ПРОГОНЕ по КАНОН-ключу (canon-URL / домен+заголовок): одна новость в 2 ПС и
    # в N запросах схлопывается в одну ДО провайдера. Кросс-чанковый дедуп — в enrich_ev (БД).
    seen, dedup = set(), []
    for it in raw:
        if not it.get('title'):
            continue
        k = _news_key(it)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(it)
    # КАПЕКС-ПРЕДФИЛЬТР: медиа-ленты (regional/google) — это firehose (lenta/ТАСС/Ъ отдают
    # 200-490 items общих новостей). Прогонять всё через провайдера дорого и шумно — сначала
    # грубый фильтр по капекс-ключам в заголовке. zakupki/hh/frp уже таргетированы — их пропускаем.
    kept = []
    for it in dedup:
        if it.get('collector') in ('regional', 'google', 'xmlriver-google', 'xmlriver-yandex',
                                   'xmlriver-gnews', 'xmlriver-ynews'):
            if not _CAPEX_KW.search(it.get('title', '')):
                continue
        kept.append(it)
    return kept


def _load_xmlriver_queries():
    """Каталог xmlriver-Google запросов с дропа (news-sources.json, ключ xmlriver_queries)."""
    try:
        url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/news-sources.json'
        req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        return json.loads(urllib.request.urlopen(req, timeout=30).read()).get('xmlriver_queries', [])
    except Exception:  # noqa: BLE001
        return []


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

    # ДИРИЖЁР ПАЙПЛАЙНА (просьба владельца): ПОСЛЕ завершения xmlriver-свипа последовательно
    # запустить обогащение: сперва news_enrich (контакты по новостным лидам — полно, с фолбэками
    # и браузером), ПОТОМ mass_base (сайты+контакты по основной базе). Лёгкий self-chaining поллер
    # (не мешает свипу; VK-свип ему безразличен — ждёт именно xmlriver). Классифицирует джобы на
    # дропе, чистит стоп-флаги фаз. Стоп: conductor_stop.flag. Переживает рестарт (seen-reset).
    if args.get('conductor'):
        import hmac as _ch, hashlib as _chl
        _drop = os.environ.get('DROP_URL', '').rstrip('/'); _tok = os.environ.get('DROP_TOKEN', '')
        _sec = os.environ.get('JOB_SECRET', '')
        _CD = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def _clist():
            return json.loads(_CD.open(urllib.request.Request(_drop + '/list', headers={'X-Drop-Token': _tok}), timeout=30).read())
        def _cget(n):
            return _CD.open(urllib.request.Request(_drop + '/' + n, headers={'X-Drop-Token': _tok}), timeout=30).read()
        def _cdel(n):
            try: _CD.open(urllib.request.Request(_drop + '/' + n, method='DELETE', headers={'X-Drop-Token': _tok}), timeout=20)
            except Exception: pass
        def _cput(jid, task, jargs):
            job = {'id': jid, 'task': task, 'args': jargs, 'ts': int(time.time())}
            canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'], 'ts': job['ts']}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            if _sec: job['sig'] = _ch.new(_sec.encode(), canon.encode(), _chl.sha256).hexdigest()
            _CD.open(urllib.request.Request(_drop + f'/job-{jid}.json', data=json.dumps(job, ensure_ascii=False).encode(), method='PUT', headers={'X-Drop-Token': _tok}), timeout=30)
        phase = args.get('phase', 'wait_sweep')
        delay = int(args.get('cond_delay', 900))
        try: _fl = _clist()
        except Exception: _fl = []
        if any(f.get('name') == 'conductor_stop.flag' for f in _fl):
            json.dump({'conductor': 'stopped-by-flag', 'phase': phase}, sys.stdout, ensure_ascii=False); return
        def _phase_active(key):   # есть ли на дропе job с этим флагом в args
            for f in _fl:
                n = f.get('name', '')
                if n.startswith('job-'):
                    try: a = json.loads(_cget(n)).get('args', {})
                    except Exception: a = {}
                    if a.get(key): return True
            return False
        sweep_active = _phase_active('sweep')   # xmlriver-свип (у VK-свипа флаг vk_sweep, не sweep)
        news_active = _phase_active('news_enrich')
        NEWS_ARGS = {'news_enrich': True, 'chain': True, 'workers': 16, 'channels': 12,
                     'pace_min': 0.4, 'pace_max': 1.2, 'stream_file': 'enrich_stream_news.jsonl',
                     'source': 'news', 'write_db': True, 'news_retry': 2, 'cap': 100}
        MASS_ARGS = {'mass_base': True, 'chain': True, 'no_site': True, 'cap': 150, 'workers': 20,
                     'channels': 12, 'no_fallback': True, 'no_browser': True, 'pace_min': 0.4,
                     'pace_max': 1.2, 'stream_file': 'enrich_stream_mass.jsonl', 'source': 'mass',
                     'write_db': True}
        def _rechain(nph):
            a = dict(args); a['phase'] = nph; a.pop('sig', None)
            _cput(f'{int(time.time())}-conductor', 'news_scan', a)
        out = {'conductor': True, 'phase': phase, 'sweep_active': sweep_active, 'news_active': news_active}
        if phase == 'wait_sweep':
            if sweep_active:
                time.sleep(delay); _rechain('wait_sweep'); out['action'] = 'wait_sweep'
            else:
                _cdel('news_stop.flag')
                _cput(f'{int(time.time())}-newsenr', 'enrich_contacts', NEWS_ARGS)
                sys.stderr.write('conductor: xmlriver-свип завершён → запускаю news_enrich\n'); sys.stderr.flush()
                time.sleep(delay); _rechain('wait_news'); out['action'] = 'started_news_enrich'
        elif phase == 'wait_news':
            if news_active:
                time.sleep(delay); _rechain('wait_news'); out['action'] = 'wait_news'
            else:
                _cdel('mass_stop.flag')
                _cput(f'{int(time.time())}-massb', 'enrich_contacts', MASS_ARGS)
                sys.stderr.write('conductor: news_enrich завершён → запускаю mass_base (дирижёр закончил)\n'); sys.stderr.flush()
                out['action'] = 'started_mass_base_done'
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    # ДИАГНОСТИКА фетча RSS: что реально видит сервер (прямой vs прокси), сколько item'ов
    # RSS-АВТОДИСКАВЕРИ: из доменов-источников (найденных xmlriver-прогонами) достаём их
    # RSS-ленты → каталог прямого (бесплатного) парсинга. args: {rss_discover:[domains]} или
    # rss_discover:'db' — собрать домены из enrich.db signals (source_url прошлых прогонов).
    if args.get('rss_discover'):
        doms = args['rss_discover']
        _ddb = None
        if doms is True or doms == 'db':   # True = как 'db' (доноры из enrich.db)
            try:
                import enrich_db as EDB
                _ddb = EDB.EnrichDB()
                # кандидаты — из таблицы donors по частоте событий (durable); те, у кого RSS
                # ещё не проверен. Фолбэк на signals, если donors пуст (старые прогоны).
                doms = _ddb.top_donor_domains(limit=int(args.get('limit', 200)), only_no_rss=True)
                if not doms:
                    rows = _ddb.cx.execute("select source_url from signals where source_url like 'http%'").fetchall()
                    cnt = {}
                    for (u,) in rows:
                        m = re.match(r'https?://([^/]+)', u or '')
                        if m:
                            cnt[m.group(1).lstrip('www.')] = cnt.get(m.group(1).lstrip('www.'), 0) + 1
                    doms = [d for d, _ in sorted(cnt.items(), key=lambda t: -t[1])[:int(args.get('limit', 200))]]
            except Exception as e:  # noqa: BLE001
                json.dump({'error': f'db:{str(e)[:80]}'}, sys.stdout, ensure_ascii=False)
                return
        found = []
        CAND = ('/rss', '/feed', '/rss.xml', '/feed.xml', '/news/rss', '/rss/news',
                '/news/feed', '/?feed=rss2', '/export/rss.xml')
        def probe_dom(d):
            base = f'https://{d}'
            # 1) стандартные пути
            for p in CAND:
                body = _get(base + p, timeout=12, tries=1)
                if body and ('<rss' in body[:2000] or '<feed' in body[:2000]):
                    n = len(_rss_items(body))
                    if n:
                        return {'domain': d, 'rss': base + p, 'items': n}
            # 2) автодискавери из HTML главной
            html = _get(base, timeout=12, tries=1)
            m = re.search(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)', html or '', re.I)
            if m:
                u = m.group(1)
                if not u.startswith('http'):
                    u = base + (u if u.startswith('/') else '/' + u)
                body = _get(u, timeout=12, tries=1)
                n = len(_rss_items(body))
                if n:
                    return {'domain': d, 'rss': u, 'items': n}
            return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(probe_dom, doms))
        for d, r in zip(doms, results):
            if r:
                found.append(r)
                if _ddb is not None:      # durable: проверенная RSS-лента донора
                    _ddb.add_donor(r['domain'], rss=r['rss'], rss_items=r['items'], status='live')
            elif _ddb is not None:        # помечаем «нет RSS» — не передискаверивать
                _ddb.add_donor(d, status='no-rss')
        json.dump({'checked': len(doms), 'found': found, 'persisted': _ddb is not None},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('site_crawl'):
        # ПОЛНЫЙ краул небольших сайтов (Meyer-база знаний): BFS по внутренним ссылкам,
        # кап страниц/сайт, текст без тегов. Результат — тексты страниц для провайдер-экстракции.
        sites = args['site_crawl']
        cap = int(args.get('pages_cap', 40))
        out = {}
        for su in sites:
            base = su if su.startswith('http') else 'https://' + su
            dom = re.match(r'https?://([^/]+)', base).group(1).lstrip('www.')
            seenu, queue, pages = set(), [base], []
            while queue and len(pages) < cap:
                u = queue.pop(0)
                if u in seenu:
                    continue
                seenu.add(u)
                html = _get(u, timeout=15, tries=2)
                if not html:
                    continue
                txt = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
                txt = re.sub(r'<[^>]+>', ' ', txt)
                txt = re.sub(r'\s+', ' ', txt).strip()
                if len(txt) > 200:
                    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
                    pages.append({'url': u, 'title': (title.group(1).strip()[:120] if title else ''),
                                  'text': txt[:14000]})
                # внутренние ссылки (без якорей/файлов)
                for l in re.findall(r'href=["\']([^"\'#]+)', html):
                    if any(l.lower().endswith(x) for x in ('.jpg', '.png', '.pdf', '.zip', '.doc',
                                                           '.docx', '.xls', '.xlsx', '.webp', '.svg')):
                        continue
                    full = l if l.startswith('http') else (f'https://{dom}' + (l if l.startswith('/') else '/' + l))
                    if re.match(r'https?://(www\.)?' + re.escape(dom), full) and full not in seenu:
                        queue.append(full.split('?')[0])
                time.sleep(_rnd.uniform(0.3, 0.8))
            out[dom] = pages
            sys.stderr.write(f'site_crawl {dom}: {len(pages)} страниц\n')
        json.dump({'sites': {d: len(p) for d, p in out.items()}, 'pages': out},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('seen_clear_after'):
        # чистка дедуп-таблицы за период (инцидент: haiku-классификатор пометил события
        # виденными, отбросив их → повторный прогон должен их переспросить)
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
            n = db.cx.execute('DELETE FROM seen_news WHERE ts >= ?',
                              (str(args['seen_clear_after']),)).rowcount
            db.cx.commit()
            json.dump({'deleted': n}, sys.stdout, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            json.dump({'error': str(e)[:100]}, sys.stdout, ensure_ascii=False)
        return
    if args.get('yandex_diag'):
        user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
        if not (user and key):
            json.dump({'error': 'нет ключей'}, sys.stdout, ensure_ascii=False); return
        q = args.get('q', '(открыли OR запустили OR "новый цех" OR завод) "Челябинск"')
        b = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
             + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop&query=')
        variants = {
            'плейн': b + urllib.parse.quote(q),
            '+y_news': b + urllib.parse.quote(q) + '&additional=y_news',
            '+within2': b + urllib.parse.quote(q) + '&within=2',
            '+within0': b + urllib.parse.quote(q) + '&within=0',
            '+date>': b + urllib.parse.quote(q + ' date:>20250401'),
            'простой-без-OR': b + urllib.parse.quote('завод Челябинск'),
            'полный-мой': b + urllib.parse.quote(q + ' date:>20250401') + '&additional=y_news&within=0',
        }
        out = {}
        for name, u in variants.items():
            body = _get(u, timeout=40)
            err = re.search(r'<error[^>]*>(.*?)</error>', body or '')
            out[name] = {'len': len(body or ''), 'docs': len(re.findall(r'<doc>', body or '')),
                         'error': (err.group(1)[:90] if err else None), 'head': (body or '')[:150]}
        json.dump({'q': q, 'variants': out}, sys.stdout, ensure_ascii=False)
        return
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
        import datetime as _dt
        week_ago = (_dt.date.today() - _dt.timedelta(days=7)).strftime('%Y%m%d')
        ybase = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
                 + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop&query=')
        variants = {
            'google-обычный': base,
            'google-новости-tbm': base + '&tbm=nws',
            'google-за-день': base + '&tbs=qdr:d',
            'google-за-неделю': base + '&tbs=qdr:w',
            'яндекс-обычный': ybase + urllib.parse.quote(q),
            'яндекс-свежее-неделя': ybase + urllib.parse.quote(f'{q} date:>{week_ago}'),
        }
        out = {}
        for name, u in variants.items():
            try:
                # _get: модульный bypass-фетч (не _NOPROXY — её затеняет локал в probe_urls ниже)
                body = _get(u, timeout=40)
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
    # VK-SWEEP: самочейнящийся ПАРАЛЛЕЛЬНЫЙ прогон VK по локациям (крупные-первыми). Джоб ЛЁГКИЙ
    # (нет xmlriver_queries → _is_heavy=False) → идёт РЯДОМ с xmlriver-свипом, не в очереди за ним.
    # Каждая локация × все _VK_PHRASES; на offset=0 добавляем нац.запросы (без гео). Тот же
    # конвейер (дедуп/seen_news/fable/БД), ссылка VK-поста → source_url лида. Стоп: vk_sweep_stop.flag.
    if args.get('vk_sweep'):
        locs = _load_vk_localities()
        offset = int(args.get('offset', 0))
        chunk = int(args.get('chunk', 6))   # 6 локаций × 20 термов = 120 запросов/чанк (под таймаут)
        loc_slice = locs[offset:offset + chunk]
        # chain В КОНЦЕ (после обработки чанка), НЕ в начале: токен VK один (~3 rps), а джоб
        # лёгкий — при chain-в-начале раннер разом фанит все чанки на воркеры и рвёт rps-лимит.
        # Пишем преемника только по завершении → ровно ОДИН VK-чанк в моменте, параллельно xmlriver.
        args['_vk_next'] = (offset + chunk) if (args.get('chain') and loc_slice
                                                and (offset + chunk) < len(locs)) else None
        phrases = args.get('vk_phrases') or _VK_PHRASES
        # ×5-ускорение (владелец 2026-07-23): vk_sleep из args (0.34 = 3 rps, лимит VK);
        # применяется вместе с chunk=30 при перезапуске цепочки
        if args.get('vk_sleep') is not None:
            globals()['_VK_SLEEP'] = float(args['vk_sleep'])
        vq = [f'{ph} {loc}' for loc in loc_slice for ph in phrases]   # гео: терм + город (без кавычек)
        args['vk_queries_built'] = vq
        args['collectors'] = ['vk']
        args.setdefault('days', 120)
        args.setdefault('write_db', True)
        args.setdefault('max_items', 4)     # кап raw/запрос (бережём fable на первом проходе)
        args.setdefault('vk_count', 50)
        sys.stderr.write(f'vk_sweep: offset={offset} локаций={len(loc_slice)} запросов={len(vq)} из {len(locs)}\n')
        sys.stderr.flush()

    # SWEEP: самочейнящийся прогон по каталогу 10к запросов (offset-курсор). Чанк обрабатывается
    # обычным конвейером (дедуп+дуал-сток+доноры), преемник пишется на дроп В НАЧАЛЕ (переживает
    # таймаут). Стоп: sweep_stop.flag или конец каталога.
    if args.get('sweep'):
        cat = _load_sweep_catalog()
        offset = int(args.get('offset', 0))
        chunk = int(args.get('chunk', 120))
        qs = cat[offset:offset + chunk]
        if args.get('chain') and qs and (offset + chunk) < len(cat):
            sys.stderr.write(f'sweep chain-next offset={offset+chunk}/{len(cat)}: '
                             f'{_chain_sweep(args, offset + chunk)}\n')
        args['xmlriver_queries'] = qs
        args['collectors'] = ['xmlriver']   # VK — отдельным параллельным vk_sweep (не мешаем)
        args.setdefault('days', 100)
        args.setdefault('write_db', True)
        sys.stderr.write(f'sweep: offset={offset} chunk={len(qs)} из {len(cat)}\n')
        sys.stderr.flush()

    token = args.get('dadata_token') or os.environ.get('DADATA_TOKEN', '')
    enrich = bool(args.get('enrich'))
    # 0 = БЕЗ ЛИМИТА (директива владельца 2026-07-23: обогащать ВСЕ лиды, не топ-N)
    enrich_max = int(args.get('enrich_max', 0))
    pace = (float(args.get('pace_min', 6.0)), float(args.get('pace_max', 14.0)))
    global _XMLR_G_WORKERS, _XMLR_Y_WORKERS
    # оптимум по замеру: Google до 10, Яндекс 6 (при 10 — медленнее из-за лимита каналов)
    _XMLR_G_WORKERS = max(1, min(int(args.get('xmlriver_g_workers', args.get('xmlriver_workers', 10))), 10))
    _XMLR_Y_WORKERS = max(1, min(int(args.get('xmlriver_y_workers', args.get('xmlriver_workers', 6))), 10))
    # капекс-классификация (extract_event) — ТОЛЬКО fable: проверено, haiku на этой задаче
    # даёт is_capex=false на явные капекс-события (терялись 99% событий, инцидент чанка №1).
    # Промпт короткий (~400 ток) → fable тут дёшев (~$15-20/полный прогон). haiku остаётся
    # на extract_roles (24к-тексты) — там его 9× экономия и качество 90% подтверждены.
    VC._PROVIDER_MODEL = args.get('extract_model', 'claude-fable-5')

    _t_collect = time.time()
    raw = collect_all(args)
    _collect_sec = round(time.time() - _t_collect, 1)
    if args.get('collect_only'):   # чистый замер сбора (xmlriver) без провайдер-пайплайна
        from collections import Counter as _CC
        json.dump({'collect_sec': _collect_sec, 'raw_items': len(raw),
                   'by_collector': dict(_CC(r.get('collector') for r in raw)),
                   'sample': [r.get('title', '')[:70] for r in raw[:8]]},
                  sys.stdout, ensure_ascii=False)
        return

    def enrich_ev(it):
        # КРОСС-ЧАНКОВЫЙ дедуп: если эту новость уже обрабатывали (др. чанк/прогон) — пропуск
        # ДО провайдера (экономия). seen_add атомарен; под локом (одно sqlite-соединение).
        if _ns_db is not None:
            with _ns_lock:
                if not _ns_db.seen_add(_news_key(it)):
                    return None
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
               'query': it.get('query', ''),   # какой запрос нашёл лид (телеметрия/ранжирование)
               'event_type': ev.get('event_type'), 'what': ev.get('what'),
               'region': ev.get('region'), 'sum': ev.get('sum'),
               'hotness': ev.get('hotness'), 'country': ev.get('country'),
               'equipment': it.get('equipment', ''),   # hh: ЧТО за оборудование стоит за наймом
               'company': ev.get('company') or it.get('company_hint'), 'is_capex': True}
        dd = dadata_suggest(rec['company'], token)
        if dd:
            rec.update({'inn': dd['inn'], 'okved': dd['okved'],
                        'company_full': dd['name'], 'status': dd['status'],
                        'dd_region': dd['region'],
                        'egrul_emails': dd.get('egrul_emails') or [],
                        'inn_confidence': dd.get('confidence', '')})
            rec['icp_fit'] = str(dd['okved']).replace('.', '')[:2] in ICP_OKVED
            rec['division'] = division_of(dd['okved'])   # kc | meyer | kc+meyer
        else:
            rec['icp_fit'] = None
            rec['division'] = None
        _persist_event(rec)   # СРАЗУ durable (jsonl + БД), не дожидаясь конца job'а
        return rec

    # СТРАХОВКА ОТ ПОТЕРИ ЛИДОВ (большой sweep): дуал-сток — (1) news_stream.jsonl append+fsync
    # (устойчив к битой строке, переживает таймаут/рестарт), (2) enrich.db. Пишем КАЖДОЕ
    # событие СРАЗУ. События БЕЗ ИНН НЕ теряем — они идут в jsonl (лид на ручной резолв).
    _ns_lock = threading.Lock()
    _wr_db = bool(args.get('write_db', True))
    _ns_jsonl = None
    _ns_db = None
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _wr_db:
        try:
            _ns_jsonl = open(os.path.join(_dir, args.get('news_stream', 'news_stream.jsonl')),
                             'a', encoding='utf-8')
        except Exception:  # noqa: BLE001
            pass
        try:
            import enrich_db as EDB
            _ns_db = EDB.EnrichDB()
        except Exception:  # noqa: BLE001
            pass

    def _persist_event(rec):
        with _ns_lock:
            if _ns_jsonl is not None:
                try:
                    _ns_jsonl.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    _ns_jsonl.flush()
                    os.fsync(_ns_jsonl.fileno())
                except Exception:  # noqa: BLE001
                    pass
            if _ns_db is not None:
                # ДОНОР: домен источника события — durable-счётчик частоты (даже без ИНН,
                # даже если событие иначе «потеряется» — донор всё равно зафиксирован).
                try:
                    dm = re.match(r'https?://([^/]+)', rec.get('source_url') or '')
                    if dm:
                        _ns_db.bump_donor(dm.group(1).lstrip('www.'))
                except Exception:  # noqa: BLE001
                    pass
                inn = str(rec.get('inn') or '')
                if inn:
                    try:
                        _ns_db.upsert_company(inn, name=rec.get('company_full') or rec.get('company'),
                                              division=rec.get('division'), okved=rec.get('okved'),
                                              region=rec.get('dd_region') or rec.get('region'))
                        _w = rec.get('what') or ''
                        if rec.get('equipment'):   # hh-тег оборудования — в текст сигнала
                            _w = (_w + ' ' if _w else '') + f'[{rec["equipment"]}]'
                        _ns_db.add_signal(inn, source=rec.get('source_name') or rec.get('collector') or 'news',
                                          event_type=rec.get('event_type') or '', what=_w,
                                          sum=str(rec.get('sum') or ''), source_url=rec.get('source_url') or '',
                                          hotness=int(rec.get('hotness') or 0), ts=rec.get('published') or '')
                        for _em in (rec.get('egrul_emails') or []):
                            _ns_db.add_email(inn, _em, role='юрзначимый (ЕГРЮЛ)',
                                             source='egrul:dadata', source_url='')
                    except Exception:  # noqa: BLE001
                        pass

    # провайдер-параллелизм: настраиваемо (владелец — 10-20 потоков вместо 1). haiku на router.cheap
    # держит; extract_event — простая капекс-классификация, потоки безопасны.
    _prov_workers = max(1, min(int(args.get('provider_workers', 12)), 64))
    with ThreadPoolExecutor(max_workers=_prov_workers) as ex:
        events = [e for e in ex.map(enrich_ev, raw) if e]
    events.sort(key=lambda e: (e.get('icp_fit') is True, e.get('hotness') or 0,
                               -(e.get('tier') or 9)), reverse=True)

    # инлайн-обогащение контактов (СЕРВЕР: сайт->роль-email, РФ-IP + обход Turnstile)
    enriched_n = 0
    if enrich and EC is not None:
        # ВСЕ лиды с компанией (владелец: «для всех, если не скажу обратное»).
        # icp_only=true вернёт старый фильтр по ОКВЭД; enrich_max>0 — жёсткий кап.
        cands = [e for e in events if e.get('company')]
        if args.get('icp_only'):
            cands = [e for e in cands if e.get('icp_fit') is not False]
        if enrich_max > 0:
            cands = cands[:enrich_max]
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

    # компания+сигнал уже записаны инкрементально в _persist_event. Здесь — только ДОЗАПИСЬ
    # email/сайта для событий, обогащённых контактами ПОСЛЕ map, + финализация jsonl-стока.
    saved = sum(1 for e in events if e.get('inn'))
    no_inn = sum(1 for e in events if not e.get('inn'))
    if _ns_db is not None:
        for e in events:
            inn = str(e.get('inn') or '')
            if not inn or not e.get('contacts'):
                continue
            try:
                c = e['contacts']
                if c.get('site') or c.get('best_for_outreach'):
                    _ns_db.upsert_company(inn, site=c.get('site'), best_email=c.get('best_for_outreach'))
                for em in (c.get('emails') or []):
                    if em.get('email'):
                        _ns_db.add_email(inn, em.get('email', ''), role=em.get('role', ''),
                                         person=em.get('person', ''), source='news',
                                         source_url=em.get('source_url') or '')
            except Exception:  # noqa: BLE001
                pass
    if _ns_jsonl is not None:
        try:
            _ns_jsonl.close()
        except Exception:  # noqa: BLE001
            pass

    # VK-свип: преемник пишется ЗДЕСЬ, в КОНЦЕ (после обработки чанка) — так на дропе всегда
    # ровно один vk_sweep-джоб, без fan-out на все воркеры (единый VK-токен, ~3 rps).
    if args.get('vk_sweep') and args.get('_vk_next') is not None:
        sys.stderr.write(f'vk_sweep chain-next offset={args["_vk_next"]}: '
                         f'{_chain_vk_sweep(args, args["_vk_next"])}\n')

    json.dump({'events': events, 'count': len(events),
               'summary': {'collectors': args.get('collectors') or ['google', 'zakupki', 'hh', 'frp'],
                           'proxy_openers': len(_OPENERS or []),
                           'raw_items': len(raw), 'capex_events': len(events),
                           'icp_fit': sum(1 for e in events if e.get('icp_fit')),
                           'with_inn': sum(1 for e in events if e.get('inn')),
                           'saved_to_db': saved, 'leads_no_inn_in_jsonl': no_inn,
                           'enriched_contacts': enriched_n,
                           'by_tier': dict(Counter(e.get('tier') for e in events)),
                           'by_collector': dict(Counter(e.get('collector') for e in events)),
                           'by_type': dict(Counter(e.get('event_type') for e in events))}},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
