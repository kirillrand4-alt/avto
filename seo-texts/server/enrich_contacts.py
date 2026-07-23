# -*- coding: utf-8 -*-
"""Обогащение контактами: ИНН/имя компании -> сайт -> страница «Контакты» ->
провайдер вытаскивает email С РОЛЯМИ (закупки/директор/гл.инженер + ФИО) ->
MX-проверка. Запускается раннером (task=enrich_contacts). Медленный темп (антибот).

stdin: {"companies":[{"inn","name","city","site"(опц.)}], "source_site":"list-org",
        "pace_min":6,"pace_max":14}
stdout: {"results":[{inn,name,site,emails:[{email,role,person,mx_ok}],
                     phones,best_for_outreach,method,error?}], "summary":{...}}"""
import os, sys, json, re, time, random, threading
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

# Параллелим МЕЖДУ компаниями (у каждой свой сайт), но ОБЩИЕ хосты держим по одному
# потоку КАЖДЫЙ — list-org и поисковик разные сайты, потому идут параллельно друг другу,
# но сами по себе не долбятся в много потоков (правило владельца «не грузить один сайт»).
_SEM_LISTORG = threading.Semaphore(1)
_SEM_SEARCH = threading.Semaphore(1)
_SEM_BROWSER = threading.Semaphore(2)   # Chromium разом (память ~300МБ каждый); main() переставит из args
# xmlriver лимитирует КАНАЛЫ аккаунта (параллельные слоты). Заливаем 500+ — отдаёт
# «Нет свободных каналов». Держим concurrency ≤ числа каналов. Настраивается под аккаунт
# (XMLRIVER_CHANNELS); дефолт 4 — консервативно, чтобы массовый прогон не выбивал лимит.
_SEM_XMLRIVER = threading.Semaphore(max(1, int(os.environ.get('XMLRIVER_CHANNELS', '4'))))
_XMLRIVER_TRIES = max(1, int(os.environ.get('XMLRIVER_TRIES', '3')))  # лёгкий ретрайт, не залипаем

# счётчики трат по сервисам (для сметы пилота) — потокобезопасно
_COST = {'xmlriver': 0, 'provider_calls': 0, 'prov_in_chars': 0, 'prov_out_chars': 0,
         'capmonster': 0, 'twocaptcha': 0}
_COST_LOCK = threading.Lock()

# браузер-фолбэк (Chromium+капча) — бесплатный, но МЕДЛЕННЫЙ (семафор 2). На массовом
# прогоне лучше выключить и гонять отдельным проходом. main() ставит из args.
_NO_BROWSER = False
# list-org/DDG фолбэк поиска сайта — под семафором=1 (сериализует ВСЕ воркеры) +
# хардкод-паузы: на массовом прогоне это главный тормоз. xmlriver и так основной канал.
_USE_FALLBACK = True
_RETURN_TEXT = False    # вернуть сырой текст сайта в результат (для офлайн модель-сравнения)
# Dolphin-фолбэк: реальный антидетект-браузер для защищённых крупных сайтов (пробивает
# managed Cloudflare/SmartCaptcha, что голый Chromium не может). Включается передачей
# dolphin_token+dolphin_profiles в args; профили ротируются по кругу.
_DOLPHIN_TOKEN = ''
_DOLPHIN_PROFILES = []
_DOLPHIN_IDX = [0]
_DOLPHIN_LOCK = threading.Lock()


# два расположения runner-secrets.env: локальный (иногда удаляется) и стабильный на дропе.
_SECRET_FILES = (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runner-secrets.env'),
                 r'C:\seostat\drop\drop-storage\runner-secrets.env')


def _read_secret(key):
    """Значение секрета: env ИЛИ любой из runner-secrets.env файлов (первый непустой)."""
    v = os.environ.get(key)
    if v:
        return v
    for p in _SECRET_FILES:
        try:
            if not os.path.exists(p):
                continue
            for line in open(p, encoding='utf-8-sig'):
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, val = line.split('=', 1)
                if k.strip() == key:
                    val = val.strip()
                    if val and not val.startswith('<'):
                        return val
        except Exception:  # noqa: BLE001
            continue
    return ''


def _parse_profile_ids(raw):
    """Список ID из строки (перевод строки/запятая/пробел) или уже-списка. Комменты '#' и пустое — вон."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        items = re.split(r'[\s,;]+', str(raw))
    out = []
    for it in items:
        it = it.strip()
        if not it or it.startswith('#'):
            continue
        it = it.split('#', 1)[0].strip()
        if it:
            out.append(it)
    # уникальные с сохранением порядка
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _cached_dolphin_profiles():
    """20 ID профилей из dolphin-profiles.txt: локальные копии → HTTP с дропа. Пусто если нигде нет."""
    paths = (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dolphin-profiles.txt'),
             r'C:\seostat\drop\drop-storage\dolphin-profiles.txt')
    for p in paths:
        try:
            if os.path.exists(p):
                ids = _parse_profile_ids(open(p, encoding='utf-8-sig').read())
                if ids:
                    return ids
        except Exception:  # noqa: BLE001
            continue
    # фолбэк: скачать с дропа
    try:
        url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/dolphin-profiles.txt'
        req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = _parse_profile_ids(r.read().decode('utf-8', 'replace'))
            if ids:
                return ids
    except Exception:  # noqa: BLE001
        pass
    return []


def _resolve_dolphin_profiles(args_profiles, token):
    """Профили дельфина в порядке надёжности: (1) явные из args → (2) live-список dolphin_list(token) →
    (3) закэшированный dolphin-profiles.txt (20 ID владельца). Живёт даже если токен протух (401)."""
    ids = _parse_profile_ids(args_profiles)
    if ids:
        return ids
    if token:
        try:
            import browser_probe as BP
            listed = BP.dolphin_list(token)
            live = [str(p.get('id')) for p in (listed or []) if p.get('id')]
            if live:
                return live
        except Exception:  # noqa: BLE001
            pass
    return _cached_dolphin_profiles()


def _opo_worker(profile, token, chunk, out_path, sleep_ms=0, start_delay=0.0):
    """ОТДЕЛЬНЫЙ ПРОЦЕСС (Playwright sync не потокобезопасен → только mp.Process): один
    дельфин-профиль, ОДНА сессия на всю пачку. checko /licenses/data?source=07 -> РТН-ОПО.
    start_delay: каскадный старт профилей (не все разом); sleep_ms: пауза между компаниями."""
    import browser_probe as _BP
    import re as _re
    import json as _json
    import random as _rnd
    from playwright.sync_api import sync_playwright
    if start_delay:
        time.sleep(start_delay)
    RTN = _re.compile(r'взрывопожароопасн|химически\s+опасн|эксплуатац\w*\s+\w*\s*опасн\w+\s+производствен|'
                      r'опасн\w+\s+производствен\w+\s+объект|маркшейдер|горн\w+\s+работ|'
                      r'гидротехническ\w+\s+сооружен', _re.I)
    # НАСТОЯЩИЙ сигнал под компрессоры (наводка владельца): вид работ "оборудование, работающее
    # под давлением >0,07 МПа" / "нагрев воды >115°C". Лицензия ВП только на горючие вещества
    # компрессоры НЕ подразумевает (напр. ДорСтрой ВП-01-003701) — а Газпром ВП-00-010849 да.
    PRESSURE = _re.compile(r'давлени\w*\s+более\s+0[.,]07|нагрева\s+воды\s+более\s+115|'
                           r'оборудован\w*,?\s*работающ\w*\s+под\s+давлением|'
                           r'сосуд\w*,?\s*работающ\w*\s+под\s+давлением|под\s+давлением\s+более', _re.I)
    LICNUM = _re.compile(r'(?:№\s*)?(?:ВП|ВХ|ЭВ|ПМ|ОТ|ГС)-\d{2}-\d{5,6}', _re.I)
    local = {}
    try:
        cdp, _port = _BP.dolphin_start(profile, headless=False, token=token)
        with sync_playwright() as pw:
            br = pw.chromium.connect_over_cdp(cdp, timeout=40000)
            ctx = br.contexts[0] if br.contexts else br.new_context()
            try:
                ctx.add_init_script(_BP._CF_INIT_JS); ctx.add_init_script(_BP._YSC_INIT_JS)
            except Exception:  # noqa: BLE001
                pass
            page = ctx.new_page()
            first = True
            for c in chunk:
                if not first and sleep_ms:
                    time.sleep(sleep_ms / 1000.0 + _rnd.uniform(0, 1.2))
                first = False
                ogrn = str(c.get('ogrn') or '').strip()
                if not ogrn:
                    local[c.get('inn', '?')] = {'error': 'нет OGRN'}; continue
                url = f'https://checko.ru/company/{ogrn}/licenses/data?source=07'
                try:
                    page.goto(url, timeout=45000, wait_until='domcontentloaded')
                    page.wait_for_timeout(2500)
                    html, cap = _BP.handle_captcha(page, url)
                    if cap or _looks_blocked(html):
                        # капча пройдена/блок: перезагружаем ЦЕЛЕВУЮ страницу (клик по
                        # «Подтвердить» не всегда возвращает на неё) и пробуем ещё раз
                        page.goto(url, timeout=45000, wait_until='domcontentloaded')
                        page.wait_for_timeout(2000)
                        html, cap = _BP.handle_captcha(page, url)
                    txt = _re.sub(r'\s+', ' ', _re.sub(r'<[^>]+>', ' ',
                                  _re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=_re.S | _re.I)))
                    local[ogrn] = {'inn': c.get('inn'), 'name': (c.get('name') or '')[:40],
                                   'sector': c.get('sector', ''), 'rtn_opo': bool(RTN.search(txt)),
                                   'pressure_equip': bool(PRESSURE.search(txt)),
                                   'lic_nums': list(set(LICNUM.findall(txt)))[:5], 'captcha': cap,
                                   'blocked': _looks_blocked(html)}
                except Exception as e:  # noqa: BLE001
                    local[ogrn] = {'inn': c.get('inn'), 'error': str(e).splitlines()[0][:80]}
            _BP.dolphin_close_tabs(br)  # не оставлять вкладки в сессии профиля (грузятся при след. старте)
            try:
                br.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        for c in chunk:
            local[str(c.get('ogrn') or c.get('inn'))] = {'error': f'session: {str(e)[:70]}'}
    finally:
        try:
            _BP.dolphin_stop(profile, token=token)
        except Exception:  # noqa: BLE001
            pass
    try:
        _json.dump(local, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def _next_dolphin_profile(skip_busy=True):
    """Следующий профиль по кругу. skip_busy: пропустить ЗАПУЩЕННЫЕ (открытые вручную/др.
    джобом) — не плодим окна и не ломимся в EBUSY (наводка владельца 2026-07-23). Проверяем
    до len(profiles) кандидатов; если все заняты — вернём очередной (пусть штатный stop-start)."""
    if not _DOLPHIN_PROFILES:
        return None
    n = len(_DOLPHIN_PROFILES)
    for _ in range(n if skip_busy else 1):
        with _DOLPHIN_LOCK:
            i = _DOLPHIN_IDX[0] % n
            _DOLPHIN_IDX[0] += 1
        pid = _DOLPHIN_PROFILES[i]
        if not skip_busy:
            return pid
        try:
            import browser_probe as _BP
            if _BP.dolphin_is_running(pid, token=_DOLPHIN_TOKEN) is True:
                continue   # занят -> следующий
        except Exception:  # noqa: BLE001
            pass
        return pid
    return _DOLPHIN_PROFILES[_DOLPHIN_IDX[0] % n]  # все заняты -> штатный (stop-start освободит)
_SKIP_PROVIDER = False  # не звать provider (только краул+regex) — быстрый сбор текстов
_NO_STAFF_SEARCH = False  # не искать staff-страницу через SERP (экономия xmlriver-квоты)
_NO_DIR_LOOKUP = False    # не искать контакты в бизнес-справочниках для компаний без сайта (#7)
_OPO_CHECK = False        # эвристическая проверка ОПО Ростехнадзора (скоринг центробежных)
_DISCOVERY_ONLY = False   # фаза-1: только найти сайт (xmlriver), краул отдельной фазой
_HH_CHECK = False         # адресная hh-проверка «ищет ли ЭТА компания компрессорщиков»
_NO_SITE_CACHE = False    # не брать сайт из кэша enrich.db (обход при ошибках кэша)
_NO_VK_LOOKUP = False     # не искать VK-группу компании (источник vk-group)
_ZAKUPKI_CHECK = False    # тянуть контакт закупщика из ЕИС в enrich_one (флаг: дорого для массы)
_SMTP_CHECK = False       # SMTP-верификация ящиков в enrich_one (флаг: сетевые пробы, дорого)


def _bump(k, n=1):
    with _COST_LOCK:
        _COST[k] = _COST.get(k, 0) + n

# переиспользуем инфраструктуру verify_company (в той же папке)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_company as VC  # _fetch, _detect_block, _provider_call_stdlib, UA

AGGREGATORS = ('otc.ru', 'rts-tender', 'roseltorg', 'sberbank-ast', 'etp-ets', 'tender',
               'zakupki', 'b2b-center', 'gz-spb', 'torgi.gov',
               'cataloxy', 'find-org', 'orgpage', 'productcenter', 'pulscen', 'tiu.ru',
               'blizko', 'firmika', 'spr.ru', 'yp.ru', 'bizly', 'rustelemarket',
               'list-org', 'rusprofile', 'checko', 'zachestnyibiznes', 'sbis.ru',
               'audit-it', 'spark-interfax', 'rbc.ru', 'sberbank', 'nalog',
               'gogov', 'kontur', 'tbank', 'saby.ru', 'openweb', 'vbankcenter',
               'wikipedia', 'yandex.', 'google.', 'youtube', '2gis', 'zoon',
               # контент-платформы/блоги — НЕ сайт компании (инцидент: dzen.ru принят
               # за сайт ООО и покраулен dzen.ru/company/staff/)
               'dzen.ru', 'vc.ru', 'tenchat', 'pikabu', 'habr', 'rutube', 'youla',
               'zen.yandex', 'т-ж.рф', 'journal.tinkoff', 'dprom.online', 'vbr.ru',
               'hh.ru', 'avito', 'flamp', 'yell.ru', 'orgpage', 'duckduckgo',
               'bing.', 'mail.ru', 'vk.com', 'telegram', 'wildberries', 'ozon',
               'rusbase', 'list-org.com', 'gis', 'dadata', 'buhonline', 'klerk',
               'audit-it', 'glavbukh', 'nalog-nalog', 'regfile', 'egrul',
               'sravni', 'banki.ru', 'consultant', 'garant', 'zakupki.gov',
               'ppt.ru', 'regforum', 'buhguru', 'nalog.gov', 'assessor.ru',
               'testfirm', 'e-ecolog', 'kompass', 'rusbizinform', 'sbis.ru',
               'rusprofile', 'spark', 'seldon', 'kartoteka', 'b2b-center',
               'export-base', 'compromat', 'otzyv', 'zoon', 'profi.ru')
CONTACT_HINTS = ('contact', 'kontakt', 'контакт', 'about', 'o-kompanii', 'o-nas',
                 'company', 'zakup', 'снабж', 'закуп', 'requisites', 'rekvizity',
                 'rukovodstvo', 'руковод', 'komanda', 'team', 'sotrudniki', 'управлен',
                 'menedzh', 'director', 'otdel', 'otdely', 'подразделен', 'prodazh',
                 'sales', 'kommerch', 'коммерч', 'filial', 'branch', 'предста', 'ofis',
                 'office', 'сбыт', 'poставщик', 'postavshchik', 'kontakty',
                 # staff-страницы (задача владельца 2026-07-23): персональные контакты по ролям
                 'staff', 'сотрудник', 'персонал', 'kollektiv', 'коллектив', 'employees')
# маркеры ИМЕННО staff-страниц (подмножество hints) — для приоритизации и решения о пробах
_STAFF_HINTS = ('staff', 'sotrudniki', 'сотрудник', 'персонал', 'kollektiv', 'коллектив',
                'komanda', 'team', 'rukovodstvo', 'руковод', 'employees')
# типовые пути staff-страниц (Bitrix-канон и частые слаги) — пробуем, если с главной
# на staff никто не ссылается; кап 2 пробы, чтобы не жечь паузы на 404
_STAFF_PROBE_PATHS = ('/company/staff/', '/staff/')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_PHONE_SITE = re.compile(r'(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')

# --- добор контактов из МЕСТ, которые теряет tag-strip: mailto/tel-ссылки, JSON-LD,
# обфусцированные адреса (info [at] domain (точка) ru, &#64;, (собака)). ---
_MAILTO_RE = re.compile(r'mailto:([^"\'?>\s]+)', re.I)
_TEL_RE = re.compile(r'tel:([+\d\s\-()]{7,})', re.I)
_JSONLD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DEOBF = [(re.compile(p, re.I), r) for p, r in (
    (r'&#0?64;|&commat;|＠|\s*[\[({]\s*(?:at|собака|эт)\s*[\])}]\s*', '@'),
    (r'\s*[\[({]\s*(?:dot|точка|тчк)\s*[\])}]\s*|\s+\(?точка\)?\s+', '.'),
)]
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')


def _harvest_from_html(blob, srcmap=None):
    """Достать email/телефоны из мест, которые не переживают вырезание тегов.
    srcmap (опц. dict) — помечает КАКИМ методом впервые найден каждый email
    (mailto/jsonld/deobf) для аналитики разметок; первый источник не перетираем."""
    emails, phones = set(), set()

    def _mark(e, method):
        if srcmap is not None and e not in srcmap:
            srcmap[e] = method
    for m in _MAILTO_RE.findall(blob or ''):
        e = m.split('?')[0].strip().lower()
        if EMAIL_RE.fullmatch(e) and not e.endswith(_IMG_EXT):
            emails.add(e)
            _mark(e, 'mailto')
    for t in _TEL_RE.findall(blob or ''):
        d = re.sub(r'\D', '', t)
        if 10 <= len(d) <= 12:
            phones.add(d)
    for js in _JSONLD_RE.findall(blob or ''):
        for e in EMAIL_RE.findall(js):
            if not e.lower().endswith(_IMG_EXT):
                emails.add(e.lower())
                _mark(e.lower(), 'jsonld')
        for t in re.findall(r'"telephone"\s*:\s*"([^"]+)"', js):
            d = re.sub(r'\D', '', t)
            if 10 <= len(d) <= 12:
                phones.add(d)
    # деобфускация: 'deobf' помечаем ТОЛЬКО email, которых в сыром тексте НЕ было,
    # а после разворачивания [at]/(точка)/&#64; появились (иначе обычные email ложно = deobf).
    raw_text = re.sub(r'<[^>]+>', ' ', blob or '')
    raw_found = set(e.lower() for e in EMAIL_RE.findall(raw_text))
    deob = raw_text
    for rx, rep in _DEOBF:
        deob = rx.sub(rep, deob)
    for e in EMAIL_RE.findall(deob):
        el = e.lower()
        if not el.endswith(_IMG_EXT):
            if el not in raw_found and el not in emails:
                _mark(el, 'deobf')
            emails.add(el)
    return emails, phones


def _PACE(a=6.0, b=14.0):
    return random.uniform(a, b)


def _domain(url):
    m = re.match(r'https?://([^/]+)', url or '')
    return (m.group(1) if m else '').lower().lstrip('www.')


def _is_own_site(url):
    d = _domain(url)
    return bool(d) and not any(a in d for a in AGGREGATORS)


def find_site_via_listorg(company):
    """Сайт компании с карточки list-org (без поисковика, надёжно)."""
    q = company.get('inn') or f"{company.get('name','')} {company.get('city','')}"
    html, method, meta = VC._fetch(f'https://www.list-org.com/search?type=inn&val={urllib.parse.quote(q)}')
    if not html or meta.get('captcha_type'):
        return None, f'listorg-block:{meta.get("captcha_type") or method}'
    ids = re.findall(r'/company/(\d+)', html)
    if not ids:
        return None, 'listorg-no-card'
    time.sleep(_PACE())
    h2, m2, meta2 = VC._fetch(f'https://www.list-org.com/company/{ids[0]}')
    if not h2 or meta2.get('captcha_type'):
        return None, f'listorg-card-block:{meta2.get("captcha_type") or m2}'
    # внешние ссылки-домены, не агрегаторы
    for u in re.findall(r'href="(https?://[^"]+)"', h2):
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'listorg-card'
    return None, 'listorg-no-site'


def find_site_via_search(company):
    """Фолбэк: поисковик (DuckDuckGo HTML) по имени+городу -> первый свой домен."""
    q = f"{company.get('name','')} {company.get('city','')} официальный сайт"
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(q)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': VC.UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, f'search-err:{str(e)[:40]}'
    for u in re.findall(r'uddg=([^"&]+)', html):
        real = urllib.parse.unquote(u)
        if _is_own_site(real):
            return f'http://{_domain(real)}', 'search'
    for u in re.findall(r'href="(https?://[^"]+)"', html):
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'search'
    return None, 'search-no-site'


# Прямой opener БЕЗ прокси — xmlriver это их инфра (капчи/банов нет), гнать через
# мобильный socks5 незачем и вредно (лишняя латентность/сбои).
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _parse_kg(xml):
    """Карточка компании (блок knowledge_graph — правая колонка Яндекса) -> dict|{}.
    Теги по доке xmlriver: type/name/website/phone/address/rating/countReviews/mapurl/id.
    email добавлен на случай, если Яндекс его отдаёт (проверяется kg_probe)."""
    m = re.search(r'<knowledge_graph\b[^>]*>(.*?)</knowledge_graph>', xml, re.S)
    if not m:
        return {}
    body = m.group(1)
    card = {}
    for tag in ('type', 'name', 'website', 'phone', 'address', 'email',
                'rating', 'countReviews', 'mapurl', 'id', 'category', 'hours'):
        mm = re.search(r'<' + tag + r'>(.*?)</' + tag + r'>', body, re.S)
        if mm:
            v = mm.group(1).strip().replace('&amp;', '&')
            if v:
                card[tag] = v
    return card


def find_site_via_xmlriver(company):
    """ОСНОВНОЙ канал: сайт компании через xmlriver (Яндекс-SERP как XML) — без капчи и
    прокси. Браузерный Яндекс/Bing с нашего IP закрыты капчей, поэтому SERP-API надёжнее.
    Один запрос с additional=knowledge_graph_y тянет И органику, И карточку компании
    (правая колонка): официальный сайт из карточки точнее первого органик-результата
    (тот бывает агрегатором/конкурентом). Возврат: (site|None, source, card_dict)."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None, 'no-xmlriver-key', {}
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    q = f'{nm} {company.get("city", "")} официальный сайт'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&additional=knowledge_graph_y&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    # «Нет свободных каналов» — это ЛИМИТ КАНАЛОВ аккаунта (не транзиент): при заливе он
    # держится, и агрессивный backoff только копит секунды и валит job по таймауту. Поэтому
    # concurrency держим низким (_SEM_XMLRIVER), а ретрай — ЛЁГКИЙ (пара попыток, короткий
    # сон на случай кратковременной конкуренции с другими окнами того же аккаунта).
    xml = None
    last = ''
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                last = 'no-free-channels'
                xml = None
                time.sleep(1.5 * (att + 1) + random.uniform(0, 1.0))
                continue
            break
        except Exception as e:  # noqa: BLE001
            last = str(e)[:40]
            time.sleep(1.5 * (att + 1))
    if xml is None:
        return None, f'xmlriver-err:{last}', {}
    card = _parse_kg(xml)
    # 1) официальный сайт прямо из карточки (правая колонка) — самый точный источник
    site_kg = card.get('website', '')
    if site_kg and _is_own_site(site_kg):
        return f'http://{_domain(site_kg)}', 'xmlriver-kg', card
    # 2) фолбэк — первый «свой» домен из органической выдачи
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'xmlriver', card
    err = re.search(r'<error[^>]*>(.*?)</error>', xml)
    return None, ('xmlriver:' + err.group(1)[:50]) if err else 'xmlriver-no-site', card


# бизнес-справочники, публикующие контакты фирм (для компаний БЕЗ своего сайта, хвост 78%).
# НЕ гос-ЭТП и НЕ финсводки (там контактов нет) — только каталоги с телефоном/почтой.
_DIR_SOURCES = ('orgpage', 'cataloxy', 'pulscen', 'tiu.ru', 'blizko', 'flamp', 'zoon',
                'yell.ru', 'spr.ru', 'firmika', 'bizly', 'rusprofile', 'list-org', '2gis')
_PHONE_RE = re.compile(r'(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')


def _egrul_emails_by_inn(inn):
    """Email из ЕГРЮЛ (юрзначимые уведомления) через dadata findById. С 2025 поле
    обязательное - покрытие высокое. Источник помечается egrul:dadata (директива владельца)."""
    tok = _read_secret('DADATA_TOKEN')
    if not (tok and inn):
        return []
    try:
        body = json.dumps({'query': str(inn)}).encode()
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
            data=body, method='POST', headers={'Content-Type': 'application/json',
            'Accept': 'application/json', 'Authorization': f'Token {tok}'})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        sugg = (d.get('suggestions') or [])
        if not sugg:
            return []
        return [e.get('value') for e in (sugg[0].get('data', {}).get('emails') or [])
                if isinstance(e, dict) and e.get('value')][:3]
    except Exception:  # noqa: BLE001
        return []


_SITE_CACHE_DAYS = 90


def _site_cache_get(inn):
    """КЭШ ИНН->сайт из enrich.db (владелец 2026-07-23: повторные компании не жгут SERP).
    TTL 90д; сайт прогоняется через _is_own_site - плохой кэш (агрегатор/контент-платформа
    из старых инцидентов) самоизлечивается. Помечается site_source=cache:enrich-db."""
    if not inn:
        return None
    try:
        import enrich_db as EDB
        import datetime as _dt
        cx = EDB.EnrichDB().cx
        row = cx.execute("SELECT site, updated_at FROM companies WHERE inn=? AND site!='' AND site IS NOT NULL",
                         (str(inn),)).fetchone()
        if not row:
            return None
        site, upd = row
        try:
            age = (_dt.datetime.now() - _dt.datetime.fromisoformat(str(upd)[:19])).days
        except Exception:  # noqa: BLE001
            age = 0
        if age > _SITE_CACHE_DAYS:
            return None
        d = _domain(str(site) if str(site).startswith('http') else 'http://' + str(site))
        if d and _is_own_site('http://' + d):
            return 'http://' + d
    except Exception:  # noqa: BLE001
        return None
    return None


_HH_COMP_KW = ('компрессор', 'воздуходув', 'компрессорн')


def find_hh_compressor(company):
    """АДРЕСНАЯ hh-проверка (владелец 2026-07-23): ищет ли ЭТА компания компрессорщиков.
    ВАЖНО: эндпоинт /employers запрещён hh ВСЕМ без авторизации (forbidden даже с домашнего
    РФ-IP - проверено владельцем). Используем ПУБЛИЧНЫЙ /vacancies: ищем вакансии
    «<компания> компрессор/воздуходув», матч работодателя по токену имени.
    Возврат: {'employer','total','compressor_vacancies':[...]} | None."""
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК)\s+', '', str(company.get('name') or '')
                ).strip().strip('"«»')
    if len(nm) < 3:
        return None
    tok = next((t.lower() for t in re.findall(r'[А-Яа-яЁёA-Za-z]{4,}', nm)), '')
    if not tok:
        return None
    _HH_UA = os.environ.get('HH_USER_AGENT', 'RuspromLeadEnrich/1.0 (kirillrand4@gmail.com)')
    def _hh_get(u):
        try:
            req = urllib.request.Request(u, headers={'User-Agent': _HH_UA, 'Accept': 'application/json'})
            d = json.loads(_DIRECT.open(req, timeout=15).read())
            if not (isinstance(d, dict) and d.get('errors')):
                return d
        except Exception:  # noqa: BLE001
            pass
        # фолбэк через дельфин (если /vacancies тоже режет IP сервера)
        try:
            import browser_probe as BP
            _dtok = _read_secret('DOLPHIN_TOKEN')
            _dp = _resolve_dolphin_profiles(None, _dtok)
            out = BP.probe({'url': u, 'return_html': True, 'html_cap': 200000, 'wait_ms': 3000,
                            'screenshot': False, 'solve': True,
                            'dolphin_profile': (_dp[0] if _dp else None), 'dolphin_token': _dtok})
            body = (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', out.get('html') or '')
            m = re.search(r'\{.*\}', body, re.S)
            return json.loads(m.group(0)) if m else {}
        except Exception:  # noqa: BLE001
            return {}
    # поиск компрессорных вакансий ИМЕННО этой компании (публичный /vacancies)
    q = f'{nm} (компрессор OR воздуходувк OR пневмат)'
    url = ('https://api.hh.ru/vacancies?text=' + urllib.parse.quote(q)
           + '&search_field=company_name&per_page=20&period=90')
    d = _hh_get(url)
    items = (d or {}).get('items') or []
    out = {'employer': None, 'total': (d or {}).get('found', 0), 'compressor_vacancies': []}
    KW = ('компрессор', 'воздуходув', 'пневмат')
    for v in items:
        emp = (v.get('employer') or {}).get('name') or ''
        if tok not in emp.lower():
            continue          # чужая компания-тёзка
        out['employer'] = out['employer'] or emp
        blob = ((v.get('name') or '') + ' '
                + str((v.get('snippet') or {}).get('requirement') or '')
                + str((v.get('snippet') or {}).get('responsibility') or '')).lower()
        if any(k in blob for k in KW):
            out['compressor_vacancies'].append({'name': v.get('name'),
                                                'url': v.get('alternate_url'),
                                                'area': (v.get('area') or {}).get('name'),
                                                'published': v.get('published_at', '')[:10]})
        if len(out['compressor_vacancies']) >= 5:
            break
    return out if out['employer'] else None


# ЕИС (zakupki.gov.ru): прямой доступ БЕЗ прокси (туннель режет госсайты) и без
# верификации TLS (Russian Trusted CA) - как в news_scan._get (проверено, работает с сервера)
_EIS_OPENER = None


def _eis_get(url, timeout=30):
    global _EIS_OPENER
    if _EIS_OPENER is None:
        import ssl as _ssl
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE
        _EIS_OPENER = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_ctx))
    req = urllib.request.Request(url, headers={'User-Agent': VC.UA, 'Accept': '*/*',
                                               'Accept-Language': 'ru-RU,ru'})
    return _EIS_OPENER.open(req, timeout=timeout).read().decode('utf-8', 'replace')


def find_zakupki_contacts(inn, max_cards=3):
    """Контакты из закупок ЕИС (директива владельца 2026-07-23). МЕХАНИКА:
    (1) RSS-поиск извещений по ИНН заказчика: /epz/order/extendedsearch/rss.html?searchString=ИНН
    (2) по ссылке каждого извещения открываем КАРТОЧКУ закупки, в ней обязательный блок
        «Контактная информация»: ФИО контактного лица, email, телефон (это снабженец/ОМТС)
    (3) тянем: ФИО + email + телефон + название закупки + ссылку карточки (source_url).
    Двойная ценность: живой контакт закупщика + сигнал «покупает» (если предмет - наше)."""
    inn = str(inn or '').strip()
    if not inn.isdigit():
        return None
    try:
        rss = _eis_get('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
                       + inn + '&fz44=on&fz223=on&sortBy=UPDATE_DATE')
    except Exception as e:  # noqa: BLE001
        return {'inn': inn, 'error': f'rss: {type(e).__name__}: {str(e)[:80]}'}
    items = re.findall(r'<item>(.*?)</item>', rss, re.S)
    out = {'inn': inn, 'rss_items': len(items), 'cards': []}
    FIO = re.compile(r'Контактное лицо\W{0,40}?([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё.]+){1,2})')
    TEL = re.compile(r'(?:Телефон|тел)\D{0,20}((?:\+7|8)[\d\s\-()]{9,18})', re.I)
    for it in items[:max_cards]:
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        if not lm:
            continue
        url = lm.group(1)
        card = {'url': url, 'title': re.sub(r'\s+', ' ', (tm.group(1) if tm else ''))[:160]}
        try:
            h = _eis_get(url)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
            fm = FIO.search(txt)
            if fm:
                card['contact_person'] = fm.group(1)
            em = [e for e in EMAIL_RE.findall(txt) if 'zakupki' not in e.lower()]
            if em:
                card['email'] = em[0].lower()
            tl = TEL.search(txt)
            if tl:
                card['phone'] = re.sub(r'\s+', ' ', tl.group(1)).strip()
        except Exception as e:  # noqa: BLE001
            card['error'] = f'{type(e).__name__}: {str(e)[:60]}'
        out['cards'].append(card)
        time.sleep(1.0 + random.uniform(0, 1.0))
    return out


_VK_PIN_PROFILE = os.environ.get('VK_DOLPHIN_PROFILE', '829115401')  # профиль, к IP которого привязан VK_TOKEN_USER


def _vk_api_via_dolphin(method, params, token):
    """Вызов VK API через дельфин. IP у ВСЕХ профилей один (владелец 2026-07-23) -> токен,
    привязанный к этому IP, работает через ЛЮБОЙ профиль. Ретраим по РАЗНЫМ профилям
    (обходим флапающий отдельный) до валидного ответа. Возврат: dict VK-ответа или {}."""
    import browser_probe as BP
    tokd = _read_secret('DOLPHIN_TOKEN')
    params = dict(params); params.update(access_token=token, v='5.199')
    u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(params)
    # ТОЛЬКО закреплённый VK-профиль: токен привязан к ЕГО IP (владелец: этот профиль по IP
    # не трогаем, остальным меняем). Один профиль -> не плодим окна. Стоп ПОСЛЕ вызова.
    pid = _VK_PIN_PROFILE
    last = {}
    for _try in range(2):   # ретрай тем же профилем (дельфин интермиттентный)
        try:
            r = BP.probe({'url': u, 'return_html': True, 'html_cap': 200000, 'wait_ms': 2500,
                          'screenshot': False, 'dolphin_profile': pid, 'dolphin_token': tokd})
            body = (r.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', r.get('html') or '')
            m = re.search(r'\{.*\}', body, re.S)
            if m:
                d = json.loads(m.group(0))
                if 'response' in d or (d.get('error') or {}).get('error_code') == 5:
                    last = d; break
                last = d
        except Exception:  # noqa: BLE001
            pass
    try:
        BP.dolphin_stop(pid, token=tokd)   # закрыть профиль после VK-вызова
    except Exception:  # noqa: BLE001
        pass
    return last


def find_vk_group_contacts(company):
    """VK-группа компании (директива владельца 2026-07-23: 70% МСБ живёт в VK).
    groups.search по имени -> верификация (сайт группы == известный сайт компании ИЛИ
    токены имени в названии/описании) -> контакты: блок «Контакты» группы (люди с РОЛЯМИ),
    email/телефоны из описания. Источник: vk-group + ссылка на группу."""
    tok = _read_secret('VK_TOKEN_USER') or _read_secret('VK_TOKEN')  # user-токен для groups.search
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК)\s+', '', str(company.get('name') or '')
                ).strip().strip('"«»')
    if not (tok and len(nm) >= 3):
        return None

    _use_dolph = bool(os.environ.get('VK_USE_DOLPHIN', '1') == '1')  # VK API через дельфин (IP-привязка)
    def _vk(method, **prm):
        if _use_dolph:
            d = _vk_api_via_dolphin(method, prm, tok)
        else:
            prm.update(access_token=tok, v='5.199')
            u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(prm)
            d = json.loads(_DIRECT.open(urllib.request.Request(u, headers={'User-Agent': VC.UA}), timeout=20).read())
        return d.get('response')

    try:
        found = (_vk('groups.search', q=nm, count=5, type='group') or {}).get('items') or []
    except Exception:  # noqa: BLE001
        return None
    tokset = [t for t in re.findall(r'[а-яёa-z]{4,}', nm.lower())][:3]
    known_dom = _domain('http://' + str(company.get('site') or '').replace('http://', '')
                        ) if company.get('site') else ''
    for g in found:
        gid = g.get('id')
        scr = g.get('screen_name') or f'club{gid}'
        try:
            info = _vk('groups.getById', group_id=gid,
                       fields='contacts,site,description,city') or []
            if isinstance(info, dict):
                info = info.get('groups') or []
            info = info[0] if info else {}
        except Exception:  # noqa: BLE001
            continue
        blob = ' '.join(str(info.get(k) or '') for k in ('name', 'description', 'site'))
        low = blob.lower()
        gdom = _domain(str(info.get('site') or '')) if info.get('site') else ''
        site_ok = bool(known_dom and gdom and gdom == known_dom)
        name_ok = bool(tokset) and all(t in low for t in tokset[:2])
        if not (site_ok or name_ok):
            continue
        emails = [e.lower() for e in EMAIL_RE.findall(blob)]
        phones = sorted({re.sub(r'[\s\-()]', '', p1) for p1 in _PHONE_SITE.findall(blob)})[:3]
        cont = []
        for c in (info.get('contacts') or [])[:6]:
            if not isinstance(c, dict):
                continue
            cont.append({'desc': c.get('desc') or '', 'phone': c.get('phone') or '',
                         'email': (c.get('email') or '').lower(), 'user_id': c.get('user_id')})
            if c.get('email'):
                emails.append(c['email'].lower())
            if c.get('phone'):
                phones.append(re.sub(r'[\s\-()]', '', c['phone']))
        if not (emails or phones or cont):
            continue
        return {'group': scr, 'url': f'https://vk.com/{scr}',
                'verified_by': 'site' if site_ok else 'name',
                'emails': sorted(set(emails))[:4], 'phones': sorted(set(phones))[:4],
                'contacts': cont, 'group_site': gdom}
    return None


def _org_page_probe(u, wait_ms=7000):
    """JS-тяжёлая страница организации (Я.Карты по mapurl / 2ГИС / zoon): рендер браузером
    (дельфин с решателем капч, если доступен) -> (text, html). Пусто при ошибке."""
    try:
        import browser_probe as BP
        pargs = {'url': u, 'return_html': True, 'html_cap': 150000,
                 'wait_ms': wait_ms, 'screenshot': False, 'solve': True}
        dpid = _next_dolphin_profile()
        if dpid and _DOLPHIN_TOKEN:
            pargs['dolphin_profile'] = dpid
            pargs['dolphin_token'] = _DOLPHIN_TOKEN
        with _SEM_BROWSER:
            out = BP.probe(pargs)
        html = out.get('html') or ''
        txt = re.sub(r'\s+', ' ', (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', html))
        return txt, html
    except Exception:  # noqa: BLE001
        return '', ''


def find_directory_contacts(company):
    """#7-фолбэк для компаний БЕЗ своего сайта: находим карточку фирмы в бизнес-справочнике
    (orgpage/cataloxy/pulscen/2gis/…) через xmlriver-SERP и извлекаем email+телефон оттуда.
    Возврат: {'source':'directory','dir_url':..,'emails':[..],'phones':[..]} | None."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    if not nm:
        return None
    q = f'{nm} {company.get("city", "")} контакты телефон email'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(1.5 * (att + 1) + random.uniform(0, 1.0))
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (att + 1))
    if xml is None:
        return None
    inn = str(company.get('inn') or '')
    # якоря идентичности: имя (первые значимые токены) + известные телефоны из базы
    name_tokens = [t for t in re.findall(r'[а-яёa-z]{4,}', nm.lower())][:3]
    base_phones = [re.sub(r'\D', '', str(p))[-10:] for p in (company.get('phones') or [])
                   if len(re.sub(r'\D', '', str(p))) >= 10]
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if not any(d in u.lower() for d in _DIR_SOURCES):
            continue
        html, _m, meta = _fetch_site(u)
        if not html or (isinstance(meta, dict) and meta.get('captcha_type')):
            # JS-тяжёлые площадки (2ГИС/zoon/Я.Карты) статикой не отдаются — рендер
            # браузером (дельфин+решатель капч). Владелец 2026-07-23: «идёт искать
            # в яндекс карты и 2гис».
            if any(d in u.lower() for d in ('2gis', 'zoon', 'yandex')):
                _t2, html = _org_page_probe(u)
            if not html:
                continue
        txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html,
                                             flags=re.S | re.I))
        low = txt.lower()
        page_phones = ''.join(re.sub(r'[\s\-()]', '', p)[-10:] for p in _PHONE_RE.findall(txt))
        # ВЕРИФИКАЦИЯ (не тёзка): ИНН на странице ИЛИ известный телефон ИЛИ имя+все токены.
        # Справочники с email часто без ИНН -> телефон/имя как якорь обязательны.
        inn_ok = bool(inn) and inn in txt.replace(' ', '')
        phone_ok = any(bp in page_phones for bp in base_phones)
        name_ok = bool(name_tokens) and all(tok in low for tok in name_tokens)
        if not (inn_ok or phone_ok or name_ok):
            continue
        emails = sorted({e.lower() for e in EMAIL_RE.findall(txt)
                         if not e.lower().endswith(_IMG_EXT)})
        phones = sorted(set(re.sub(r'[\s\-()]', '', p) for p in _PHONE_RE.findall(txt)))
        if emails or phones:
            return {'source': 'directory', 'dir_url': u, 'verified_by':
                    'inn' if inn_ok else ('phone' if phone_ok else 'name'),
                    'emails': emails[:5], 'phones': phones[:3]}
    return None


# ОПО Ростехнадзора: рег-номер объекта (А##-#####[-####]) + типы «компрессорных» объектов.
_OPO_NUM = re.compile(r'\bА\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?\b')
_OPO_OBJ = re.compile(
    r'(компрессорн\w+\s+станц\w+|станц\w+\s+компрессорн\w+|воздухоразделит\w+|'
    r'площадк\w+\s+компрессорн\w+|газоперекачив\w+|сеть\s+газопотреблен\w+|'
    r'станц\w+\s+газораспределит\w+)', re.I)


def find_opo_signal(company):
    """Эвристический маркер ОПО Ростехнадзора (скоринг центробежных): SERP по компании +
    маркеры опасного производственного объекта. Ловит рег-номер и тип объекта из сниппетов.
    Возврат: {'opo':True,'opo_object':..,'opo_reg':..,'source_url':..} | None. НЕ авторитетно —
    буст приоритета для кандидатов, найденных hh/ЕИС/ОКВЭД."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    if not nm:
        return None
    q = f'{nm} {company.get("city","")} опасный производственный объект компрессорная станция реестр Ростехнадзор'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(1.5 * (att + 1) + random.uniform(0, 1.0))
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (att + 1))
    if xml is None:
        return None
    # ВАЖНО (владелец: «приходит пустой/обрезанный, а ты видишь крутится»): разбираем ОТДЕЛЬНЫЕ
    # результаты, а не общий свал сниппетов. Тип объекта И контекст «опасн/ОПО/Ростехнадзор»
    # должны быть в ОДНОМ результате, и источник — НЕ обобщённая юр-справка (закон/приказ
    # ОПРЕДЕЛЯЕТ термин «площадка компрессорной станции», но не доказывает ОПО у ЭТОЙ компании).
    LAW_REF = ('sudact.ru/law', 'consultant.ru', 'garant.ru', 'cntd.ru', 'kodeks',
               'pravo.gov', 'normativ', 'zakonbase', 'legalacts', 'base.garant',
               '/law/', 'zakonrf', 'gostrf', 'docs.cntd', 'ohranatruda')
    AUTH = ('e-ecolog.ru', 'gosnadzor', 'rusprofile.ru', 'checko.ru', 'list-org',
            'audit-it', 'zachestnyibiznes')   # авторитетнее как доказательство ОПО
    _ctx_re = re.compile(r'опасн\w+\s+производствен|ОПО|Ростехнадзор|промышленн\w+\s+безопасн', re.I)
    # разбиваем выдачу на per-результатные куски по границам <url> (устойчиво к тому, обёрнуты
    # ли результаты в <doc>/<group> или нет — иначе легко получить 0 из-за формата, а не данных).
    parts = re.split(r'(?=<url>)', xml)
    best = None
    for dm in parts:
        um = re.search(r'<url>(.*?)</url>', dm, re.S)
        if not um:
            continue
        u = um.group(1).strip(); ul = u.lower()
        if any(l in ul for l in LAW_REF):
            continue   # юр-справка/определение термина — не доказательство ОПО у компании
        sn = re.sub(r'<[^>]+>', ' ', dm)
        obj = _OPO_OBJ.search(sn)
        if not obj:
            continue
        is_auth = any(a in ul for a in AUTH)
        # авторитетный источник (e-ecolog/gosnadzor/rusprofile) + тип объекта = принимаем;
        # прочие — только если контекст «опасн/ОПО/Ростехнадзор» в ЭТОМ ЖЕ результате.
        if not (is_auth or _ctx_re.search(sn)):
            continue
        num = _OPO_NUM.search(sn)
        cand = {'opo': True, 'opo_object': obj.group(0),
                'opo_reg': num.group(0) if num else '', 'source_url': u}
        if is_auth:
            return cand
        if best is None:
            best = cand
    return best


def find_staff_via_search(company, dom):
    """Поисковый этап (2026-07-23): найти страницу СОТРУДНИКОВ/КОМАНДЫ компании через
    xmlriver-SERP, даже если она нестандартно названа и не слинкована с главной.
    Запрос «компания + команда/сотрудники/руководство», из выдачи берём URL НА ДОМЕНЕ
    компании (dom) со staff-подсказкой в пути. Возврат: список URL (0-3)."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key and dom):
        return []
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    q = f'{nm} команда сотрудники руководство'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(1.5 * (att + 1) + random.uniform(0, 1.0))
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (att + 1))
    if xml is None:
        return []
    out = []
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if _domain(u) != dom:
            continue                       # только собственный домен компании
        ul = u.lower()
        if any(h in ul for h in _STAFF_HINTS) or any(h in ul for h in ('kontakt', 'контакт', 'about', 'company')):
            if u not in out:
                out.append(u)
        if len(out) >= 3:
            break
    return out


def crawl_contacts(site, pace=(6.0, 14.0), extra_pages=None):
    """Домашняя + страницы контактов/сотрудников -> объединённый текст (кап по объёму).

    П-staff (2026-07-23): по каждой странице ДО склейки извлекаем email отдельно,
    чтобы знать URL-источник каждого контакта (url_first); staff-ссылки идут в
    обход первыми; если главная на staff не ссылается — пробуем типовые пути.
    extra_pages — URL staff-страниц, найденные ПОИСКОМ (find_staff_via_search):
    покрывают сайты, где страница названа нестандартно и не слинкована с главной."""
    pages, texts = [], []
    if not site.startswith('http'):
        site = 'http://' + site   # страховка: _domain на голом домене даёт пустой netloc
    home, method, meta = _fetch_site(site)
    if not home or meta.get('captcha_type'):
        # ДЫРА закрыта (владелец 2026-07-23): сайт закрыт капчей/антиботом С ПОРОГА —
        # раньше бросали с пометкой «блок». Теперь рендер браузером с решателем капч
        # (дельфин): решённая главная даёт и текст, и ссылки для обычного обхода.
        if not _NO_BROWSER:
            _bt, _bh = _org_page_probe(site, wait_ms=9000)
            if _bh and not _looks_blocked(_bh):
                home, method, meta = _bh, 'browser-solved', {}
    if not home or meta.get('captcha_type'):
        return '', [], f'site-block:{meta.get("captcha_type") or method}', {}
    dom = _domain(site)
    texts.append(home)
    page_htmls = [(f'http://{dom}/', home)]   # (url, html) — для атрибуции email->страница
    links = re.findall(r'href="([^"]+)"', home)
    picked = []
    # найденные поиском staff-URL — В НАЧАЛО (высший приоритет, покрывают любые вариации)
    for u in (extra_pages or []):
        if _domain(u) == dom and u not in picked:
            picked.append(u)
    for l in links:
        ll = l.lower()
        if any(h in ll for h in CONTACT_HINTS):
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/"+l}'
            if _domain(full) == dom and full not in picked:
                picked.append(full)
        if len(picked) >= 10:
            break
    # приоритет обхода (владелец 2026-07-23): staff (персональные контакты) ->
    # закупки/снабжение/поставщикам (контакты закупщиков - целевые ЛПР) -> остальное.
    # Сортировка стабильная - внутри групп порядок ссылок сайта сохраняется.
    _PROC_HINTS = ('zakup', 'закуп', 'снабж', 'постав', 'postav', 'tender', 'тендер')
    def _crawl_prio(u):
        ul = u.lower()
        if any(h in ul for h in _STAFF_HINTS):
            return 0
        if any(h in ul for h in _PROC_HINTS):
            return 1
        return 2
    picked.sort(key=_crawl_prio)
    # с главной на staff никто не ссылается -> пробуем типовые пути (Bitrix-канон);
    # неудачная проба вернёт пусто из _fetch_site и просто не попадёт в texts
    if not any(any(h in u.lower() for h in _STAFF_HINTS) for u in picked):
        for p in _STAFF_PROBE_PATHS:
            full = f'http://{dom}{p}'
            if full not in picked:
                picked.append(full)
    for u in picked:
        time.sleep(_PACE(*pace))
        h, m, mt = _fetch_site(u)
        if h and not mt.get('captcha_type'):
            texts.append(h)
            pages.append(u)
            page_htmls.append((u, h))
    # ВТОРОЙ УРОВЕНЬ (владелец 2026-07-23): проваливаемся ВНУТРЬ страниц контактов/staff —
    # мульти-офисные сайты держат карточки офисов/отделов/филиалов на ПОДстраницах
    # (/contacts/moscow, /contacts/otdel-prodazh), с главной на них ссылок нет. Со всех
    # собранных страниц берём ссылки с теми же хинтами, которых ещё не обходили. Бюджет +8.
    lvl2 = []
    _seen_u = {x[0] for x in page_htmls}
    for _u, _h in list(page_htmls[1:]):
        for l in re.findall(r'href="([^"]+)"', _h):
            if l.startswith(('mailto:', 'tel:', '#', 'javascript:')):
                continue
            ll = l.lower()
            if not any(h2 in ll for h2 in CONTACT_HINTS):
                continue
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/" + l}'
            if _domain(full) == dom and full not in _seen_u and full not in lvl2:
                lvl2.append(full)
    for u in lvl2[:8]:
        time.sleep(_PACE(*pace))
        h, m, mt = _fetch_site(u)
        if h and not mt.get('captcha_type'):
            texts.append(h)
            pages.append(u)
            page_htmls.append((u, h))
    # П-staff: ПАГИНАЦИЯ списков сотрудников (Bitrix ?PAGEN_n=2, ?page=2, /page/2/).
    # Идём по страницам, пока КАЖДАЯ даёт новые email: Bitrix за концом диапазона
    # отдаёт первую страницу заново — дубль не даст новых и остановит обход. Кап 5.
    def _page_emails(h):
        _es, _ = _harvest_from_html(h)
        _t = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                            flags=re.S | re.I))
        for _e in EMAIL_RE.findall(_t):
            _es.add(_e.lower())
        return {e for e in _es if not e.endswith(_IMG_EXT)}
    seen_pg = set()
    for _u, _h in page_htmls:
        seen_pg |= _page_emails(_h)
    for src_u, src_h in list(page_htmls[1:]):   # пагинация доп-страниц (staff/контакты)
        pag = re.findall(r'href="([^"]*(?:PAGEN_\d+=\d+|[?&]page=\d+|/page/\d+/?)[^"]*)"',
                         src_h)
        cands, added = [], 0
        for l in pag:
            l = l.replace('&amp;', '&')
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/" + l}'
            if _domain(full) == dom and full not in cands:
                cands.append(full)
        for pu in cands[:6]:
            if any(pu == x[0] for x in page_htmls):
                continue
            time.sleep(_PACE(*pace))
            ph, _pm, pmt = _fetch_site(pu)
            if not ph or pmt.get('captcha_type'):
                continue
            new = _page_emails(ph) - seen_pg
            if not new:
                continue   # дубль первой страницы / пустая — стоп-сигнал, не копим
            seen_pg |= new
            texts.append(ph)
            pages.append(pu)
            page_htmls.append((pu, ph))
            added += 1
            if added >= 5:
                break
    # атрибуция ДО склейки: email -> URL первой страницы, где он найден. Порядок обхода
    # (главная -> staff -> контакты) даёт правильный источник: info@ атрибутируется
    # главной, персональные — staff-странице.
    url_first = {}
    for _u, _h in page_htmls:
        _pe, _ = _harvest_from_html(_h)
        _pt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', _h,
                                             flags=re.S | re.I))
        for _e in EMAIL_RE.findall(_pt):
            _pe.add(_e.lower())
        for _e in _pe:
            if not _e.endswith(_IMG_EXT):
                url_first.setdefault(_e, _u)
    # склеиваем текст, режем теги, кап.
    # П-staff: ДО вырезания тегов инлайним mailto/tel В ТЕКСТ рядом с местом ссылки —
    # иначе email из href исчезает и провайдер не может связать «ФИО + должность + email»
    # (на staff-страницах контакты живут ТОЛЬКО в href, текст ссылки часто «написать»).
    texts = [re.sub(r'<a\s[^>]*href="mailto:([^"?]+)[^"]*"[^>]*>', r' [email: \1] <a>', t)
             for t in texts]
    texts = [re.sub(r'<a\s[^>]*href="tel:([^"]+)"[^>]*>', r' [тел: \1] <a>', t)
             for t in texts]
    blob = ' '.join(texts)
    txt = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', blob, flags=re.S | re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    # ДОБОР из мест, которые теряет tag-strip: mailto/tel-ссылки, JSON-LD, обфускация.
    # srcmap помечает КАКИМ методом найден каждый email (для разбора разметок).
    srcmap = {}
    h_emails, h_phones = _harvest_from_html(blob, srcmap)
    for e in set(EMAIL_RE.findall(txt)):   # обычный видимый текст — базовый метод
        el = e.lower()
        if not el.endswith(_IMG_EXT):
            srcmap.setdefault(el, 'text')
    if h_emails or h_phones:
        txt = txt + ' Контакты(добор): ' + ' '.join(sorted(h_emails)) + ' ' + ' '.join(sorted(h_phones))
    # JS-email: если email НЕ найден НИГДЕ (ни в тексте, ни в доборе) — он мог отрисоваться
    # скриптом → рендерим главную в браузере (Playwright исполнит JS).
    if not EMAIL_RE.search(txt) and not h_emails and not _NO_BROWSER:
        try:
            import browser_probe as BP
            pargs = {'url': site, 'return_html': True, 'html_cap': 130000,
                     'wait_ms': 5000, 'screenshot': False, 'solve': True}
            dpid = _next_dolphin_profile()
            if dpid and _DOLPHIN_TOKEN:
                # Dolphin: пробивает защиту крупных сайтов (свой fingerprint+socks5)
                pargs['dolphin_profile'] = dpid
                pargs['dolphin_token'] = _DOLPHIN_TOKEN
                pargs['wait_ms'] = 8000
            with _SEM_BROWSER:
                out = BP.probe(pargs)
            if out.get('captcha_solved') or out.get('cf_solved'):
                _bump('twocaptcha' if out.get('captcha_type') == 'smartcaptcha' else 'capmonster')
            bhtml = out.get('html') or ''
            btxt = (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', bhtml)
            _harvest_from_html(bhtml, srcmap)  # дораскладываем источники из JS-рендера
            for e in set(EMAIL_RE.findall(btxt)):
                el = e.lower()
                if not el.endswith(_IMG_EXT):
                    srcmap.setdefault(el, 'js-render')
            txt = re.sub(r'\s+', ' ', txt + ' ' + btxt)
        except Exception:  # noqa: BLE001
            pass
    from collections import Counter as _C
    csrc = dict(_C(srcmap.values()))
    # по каждому email: метод-источник + local-part + контекст вокруг (±70 симв) —
    # чтобы офлайн понять, извлекается ли РОЛЬ скриптом (local-part/метка) или это «каша».
    low = txt.lower()
    per = {}
    home_url = f'http://{dom}/'
    for e in srcmap:
        pos = low.find(e)
        ctx = re.sub(r'\s+', ' ', txt[max(0, pos - 70):pos + len(e) + 20]).strip() if pos >= 0 else ''
        # url: страница, где email найден впервые; js-render-контакты — с главной
        per[e] = {'src': srcmap[e], 'local': e.split('@')[0], 'ctx': ctx,
                  'url': url_first.get(e, home_url if srcmap[e] == 'js-render' else '')}
    csrc['emails'] = per
    return txt[:28000], pages, None, csrc


def extract_roles(text, company):
    """Провайдер: email С РОЛЯМИ + ЛПР для холодного письма. Фолбэк — regex."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    provider_attempted = False
    if key and EMAIL_RE.search(text):
        provider_attempted = True   # провайдер ДОЛЖЕН был отработать (есть ключ и email в тексте)
        prompt = (
            'Из текста сайта компании извлеки контакты С РОЛЯМИ и ПОДТВЕРДИ, что сайт '
            f'принадлежит именно этой компании. Компания: «{company.get("name","")}»'
            + (f', ИНН {company.get("inn")}' if company.get('inn') else '')
            + (f', город {company.get("city")}' if company.get('city') else '') + '. '
            'Также определи по тексту главной, ЧЕМ занимается компания, и НЕ является ли она '
            'сама производителем/продавцом компрессоров, насосов, компрессорного оборудования '
            '(тогда это КОНКУРЕНТ, а не покупатель — таким не пишем). '
            'Верни СТРОГО JSON без markdown: '
            '{"owner_match":true/false,"owner_reason":"почему сайт этой/не этой компании",'
            '"activity":"1 короткая фраза чем занимается компания (для персонализации письма)",'
            '"is_compressor_maker":true/false,'
            '"emails":[{"email":"","role":"директор|снабжение/закупки|гл.инженер|'
            'продажи|бухгалтерия|приёмная|общий","person":"ФИО или пусто"}],'
            '"phones":[""],"best_for_outreach":"email ЛПР для холодного письма '
            '(приоритет закупки>гл.инженер>директор>продажи>общий)"}. '
            'owner_match=false если сайт — агрегатор/каталог/тёзка/другая фирма. '
            'Бери только email этой компании (её домен), не сторонние. Текст:\n' + text[:24000])
        out = None
        for _ in range(3):
            try:
                out = VC._provider_call_stdlib(prompt)
                _bump('provider_calls')
                _bump('prov_in_chars', len(prompt))
                _bump('prov_out_chars', len(out or ''))
                if out:
                    m = re.search(r'\{.*\}', out, re.S)
                    if m:
                        return json.loads(m.group(0)), 'provider'
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
    # regex-фолбэк: email без ролей. Если провайдер БЫЛ должен отработать, но упал 3× —
    # помечаем 'regex-provider-fail' → done-set исключит на перепроверку (провайдер лежал).
    emails = sorted(set(e.lower() for e in EMAIL_RE.findall(text)
                        if not e.lower().endswith(('.png', '.jpg', '.gif', '.webp'))))
    how = 'regex-provider-fail' if provider_attempted else 'regex'
    return {'emails': [{'email': e, 'role': 'общий', 'person': ''} for e in emails[:8]],
            'phones': [], 'best_for_outreach': emails[0] if emails else ''}, how


def mx_ok(email):
    """Быстрая проверка MX домена email (nslookup, stdlib-фолбэк)."""
    dom = email.split('@')[-1] if '@' in email else ''
    if not dom:
        return False
    try:
        import subprocess
        out = subprocess.run(['nslookup', '-type=MX', dom], capture_output=True,
                             text=True, timeout=12).stdout.lower()
        return 'mail exchanger' in out or 'mx preference' in out
    except Exception:  # noqa: BLE001
        return None  # не смогли проверить — не роняем


def smtp_verify(email, mail_from='postmaster@parsercompressor.online', timeout=12):
    """SMTP-проба существования ящика через RCPT TO БЕЗ отправки (владелец 2026-07-23).
    Возврат: 'smtp_ok' | 'catch-all' | 'smtp_reject' | 'unknown' | 'no_mx' | 'port25_blocked'.
    catch-all: сервер принимает случайный несуществующий адрес -> проверить нельзя.
    Аккуратно: 1 коннект на домен, короткий таймаут, пауза зовущим кодом."""
    dom = email.split('@')[-1].lower() if '@' in email else ''
    if not dom:
        return 'unknown'
    # MX-хосты домена (nslookup, т.к. dnspython может отсутствовать)
    mxs = []
    try:
        import subprocess
        out = subprocess.run(['nslookup', '-type=MX', dom], capture_output=True,
                             text=True, timeout=10).stdout
        for m in re.findall(r'mail exchanger\s*=\s*(\S+)', out) or re.findall(r'MX preference.*?mail exchanger\s*=\s*(\S+)', out, re.I):
            mxs.append(m.strip().rstrip('.'))
        if not mxs:
            for m in re.findall(r'=\s*\d+\s+(\S+\.\S+)', out):
                mxs.append(m.strip().rstrip('.'))
    except Exception:  # noqa: BLE001
        pass
    if not mxs:
        return 'no_mx'
    import smtplib as _smtp
    import socket as _sock
    host = mxs[0]
    try:
        srv = _smtp.SMTP(timeout=timeout)
        srv.connect(host, 25)
        srv.helo('parsercompressor.online')
        srv.mail(mail_from)
        code_real, _ = srv.rcpt(email)
        # контроль catch-all: заведомо несуществующий ящик того же домена
        import hashlib as _hl
        fake = 'nx' + _hl.md5(email.encode()).hexdigest()[:10] + '@' + dom
        code_fake, _ = srv.rcpt(fake)
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
        if code_fake in (250, 251):
            return 'catch-all'          # принимает всё -> не показатель
        if code_real in (250, 251):
            return 'smtp_ok'
        if code_real in (550, 551, 553, 554, 501):
            return 'smtp_reject'        # ящика нет -> ВЫКИНУТЬ
        return 'unknown'
    except (_sock.timeout, _smtp.SMTPConnectError, _sock.error, OSError):
        return 'port25_blocked'
    except Exception:  # noqa: BLE001
        return 'unknown'


# Маркеры РЕАЛЬНОЙ страницы-заглушки (интерстишла), а НЕ виджета капчи в форме.
# Важно: 'g-recaptcha'/'cf-turnstile'/'smartcaptcha' часто стоят в форме обратной связи
# на ПОЛНОЦЕННОЙ странице (со всем контентом и email) — это НЕ блок. Блоком считаем
# только когда это интерстишл: короткая страница + маркер проверки браузера.
_INTERSTITIAL = ('just a moment', 'ddos-guard', 'checking your browser', 'attention required',
                 'проверка, что вы', 'подтвердите, что вы человек', 'один момент',
                 'cf-chl', 'challenge-platform')


def _looks_blocked(html):
    b = (html or '').lower()
    if not b or len(b) < 500:
        return True                          # пусто/обрывок — считаем блоком
    if any(m in b for m in _INTERSTITIAL):
        return True                          # явная страница-заглушка
    # «вы не робот» как ОСНОВНОЙ контент (короткая страница) — тоже заглушка
    if 'вы не робот' in b and len(b) < 8000:
        return True
    return False                             # виджет-капча в форме на живой странице — не блок


def _fetch_site(url):
    """Краул сайта компании: сперва ПРЯМО (датацентр-IP; сайты компаний его не банят, в
    отличие от поисковиков — надёжнее флаки-socks5, терпит IncompleteRead), при блоке/капче
    — фолбэк на VC._fetch (прокси + CapMonster-решатель Turnstile)."""
    try:
        u = VC._norm_url(url)
    except Exception:  # noqa: BLE001
        u = url
    html = ''
    try:
        req = urllib.request.Request(u, headers={
            'User-Agent': VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with _DIRECT.open(req, timeout=30) as r:
            try:
                raw = r.read()
            except Exception as e:  # noqa: BLE001  IncompleteRead -> частичное
                raw = getattr(e, 'partial', b'') or b''
            html = raw.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:  # noqa: BLE001
        try:
            html = e.read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            html = ''
    except Exception as e:  # noqa: BLE001
        html = (getattr(e, 'partial', b'') or b'').decode('utf-8', 'replace')
    if html and not _looks_blocked(html):
        return html, 'direct', {}
    # фолбэк 1: прокси + CapMonster-решатель Turnstile (Cloudflare)
    h2, m2, meta2 = VC._fetch(u)
    if h2 and not meta2.get('captcha_type'):
        return h2, m2, meta2
    # фолбэк 2: рендер в браузере + решатель reCAPTCHA v2 (CapMonster) / Cloudflare —
    # для сайтов за reCAPTCHA/антиботом, которые urllib не проходит (напр. betaren.ru)
    if _NO_BROWSER:
        return (h2 or None), (m2 if h2 else f'site-block:{(meta2 or {}).get("captcha_type") or "no-browser"}'), (meta2 or {})
    try:
        import browser_probe as BP
        with _SEM_BROWSER:
            out = BP.probe({'url': u, 'solve': True, 'return_html': True,
                            'html_cap': 130000, 'wait_ms': 6000, 'screenshot': False})
        if out.get('captcha_solved') or out.get('cf_solved'):
            _bump('twocaptcha' if out.get('captcha_type') == 'smartcaptcha' else 'capmonster')
        bh = out.get('html', '') or ''
        if bh and not _looks_blocked(bh):
            return bh, 'browser-solved', {}
        # фолбэк 3: ДЕЛЬФИН (антидетект-профиль: свой fingerprint + socks5) — пробивает
        # сайты, которые режут обычный Playwright по браузерному отпечатку/датацентр-IP.
        dpid = _next_dolphin_profile()
        if dpid and _DOLPHIN_TOKEN:
            try:
                with _SEM_BROWSER:
                    dout = BP.probe({'url': u, 'solve': True, 'return_html': True,
                                     'html_cap': 130000, 'wait_ms': 8000, 'screenshot': False,
                                     'dolphin_profile': dpid, 'dolphin_token': _DOLPHIN_TOKEN})
                if dout.get('captcha_solved') or dout.get('cf_solved'):
                    _bump('twocaptcha' if dout.get('captcha_type') == 'smartcaptcha' else 'capmonster')
                dh = dout.get('html', '') or ''
                if dh and not _looks_blocked(dh):
                    return dh, 'dolphin-solved', {}
            except Exception:  # noqa: BLE001
                pass
        return (h2 or bh), f'site-block:{out.get("captcha_type") or "browser"}', \
            {'captcha_type': out.get('captcha_type') or (meta2 or {}).get('captcha_type')}
    except Exception as e:  # noqa: BLE001
        return (h2 or None), (m2 if h2 else f'browser-err:{str(e)[:40]}'), (meta2 or {})


_COMP_OKVED = ('28.13', '28.12')             # производство насосов/компрессоров/пневмо
_COMP_NAME = re.compile(
    r'компрессормаш|компрессорн\w*\s*завод|завод\w*\s*компрессор|'
    r'насосн\w*\s*завод|компрессорн\w*\s*оборудован', re.I)


def _is_competitor(company):
    """Дешёвый пре-фильтр: производитель компрессоров/насосов = конкурент, не покупатель."""
    okv = str(company.get('okved') or '')
    if any(okv.startswith(x) for x in _COMP_OKVED):
        return True
    return bool(_COMP_NAME.search(company.get('name', '') or ''))


def _finalize_smtp(r):
    """SMTP-верификация email результата (флаг _SMTP_CHECK). Каждому email -> поле smtp
    (smtp_ok/catch-all/smtp_reject/...); smtp_reject исключается из best_for_outreach (на
    мёртвые не шлём - защита репутации домена). Кэш по домену: один диалог на домен. Кап 6."""
    ems = r.get('emails') or []
    if not ems:
        return r
    dom_cache = {}
    checked = 0
    for e in ems:
        addr = (e.get('email') or '').lower()
        if not addr or '@' not in addr:
            continue
        dom = addr.split('@')[-1]
        # catch-all определяется по домену -> но RCPT по адресу; кэшируем статус catch-all
        if checked >= 6:
            break
        st = smtp_verify(addr)
        e['smtp'] = st
        checked += 1
        if st == 'catch-all':
            dom_cache[dom] = 'catch-all'
        time.sleep(1.2)
    # best_for_outreach не должен быть заведомо мёртвым
    best = r.get('best_for_outreach')
    if best:
        bmap = {e.get('email', '').lower(): e.get('smtp') for e in ems}
        if bmap.get(best.lower()) == 'smtp_reject':
            alt = next((e['email'] for e in ems
                        if e.get('smtp') in ('smtp_ok', 'catch-all', None, 'unknown', 'port25_blocked')
                        and e.get('email', '').lower() != best.lower()), '')
            r['best_for_outreach'] = alt
            r['smtp_note'] = f'исходный best {best} = smtp_reject, заменён'
    return r


def enrich_one(company, pace):
    r = {'inn': company.get('inn'), 'name': company.get('name')}
    # пре-фильтр конкурентов (производители компрессоров) — не тратим на них разведку
    if _is_competitor(company):
        r.update({'method': 'competitor-skip', 'is_competitor': True,
                  'error': 'конкурент (производитель компрессоров/насосов)'})
        return r
    # ОПО-сигнал (скоринг центробежных): эвристический маркер опасного производственного
    # объекта. Флаг opo_check; результат — в r['opo'] независимо от того, найдутся ли контакты.
    if _OPO_CHECK:
        try:
            opo = find_opo_signal(company)
            if opo:
                r['opo'] = opo
        except Exception:  # noqa: BLE001
            pass
    # адресный hh-сигнал: у ЭТОЙ компании открыты компрессорные вакансии = оборудование
    # есть/появляется (прямое подтверждение, не «расширение вообще»)
    if _HH_CHECK:
        try:
            hh = find_hh_compressor(company)
            if hh:
                r['hh'] = hh
        except Exception:  # noqa: BLE001
            pass
    # ЕИС-закупки: контакт закупщика (ФИО+email+тел) из карточек госзакупок компании
    # (владелец 2026-07-23: влить в общий конвейер). source zakupki:eis.
    if _ZAKUPKI_CHECK and company.get('inn'):
        try:
            z = find_zakupki_contacts(company['inn'], max_cards=3)
            if z and z.get('cards'):
                r['zakupki'] = z
                _zem = []
                for c in z['cards']:
                    if c.get('email'):
                        _zem.append({'email': c['email'].lower(), 'role': 'закупки (конт. лицо)',
                                     'person': c.get('contact_person') or '', 'mx_ok': mx_ok(c['email']),
                                     'source': 'zakupki:eis', 'source_url': c.get('url') or '',
                                     'verified_by': 'inn'})
                if _zem:
                    r['emails'] = (r.get('emails') or []) + _zem
                    if not r.get('best_for_outreach'):
                        r['best_for_outreach'] = _zem[0]['email']
        except Exception:  # noqa: BLE001
            pass
    site = company.get('site')
    src = 'given'
    card = {}
    tmr = {}
    if not site or not _is_own_site(site if site.startswith('http') else 'http://' + site):
        # ОСНОВНОЙ канал — xmlriver (чистый SERP, без капчи/прокси); фолбэки — list-org и
        # DDG под семафором=1 (не грузить один хост). На массовом прогоне фолбэки ЖГУТ
        # время (сериализуют все воркеры + хардкод-паузы) — _USE_FALLBACK их выключает.
        _t0 = time.time()
        # кэш ИНН->сайт: выключается no_site_cache (если полезут ошибки - источник виден
        # по site_source='cache:enrich-db')
        site = None
        if not _NO_SITE_CACHE:
            site = _site_cache_get(company.get('inn'))
            if site:
                src = 'cache:enrich-db'
        if not site:
            site, src, card = find_site_via_xmlriver(company)
        if not site and _USE_FALLBACK:
            with _SEM_LISTORG:
                site, src = find_site_via_listorg(company)
                time.sleep(_PACE(1.5, 4.0))
        if not site and _USE_FALLBACK:
            with _SEM_SEARCH:
                site, src = find_site_via_search(company)
                time.sleep(_PACE(1.5, 4.0))
        if not site and company.get('base_site'):
            # последний фолбэк: известный сайт из базы [20] (news_enrich кладёт его сюда,
            # чтобы первичным был xmlriver, но не терять базовый сайт, если поиск не нашёл)
            bs = company['base_site']
            bsf = bs if bs.startswith('http') else 'http://' + bs
            if _is_own_site(bsf):
                site, src = bsf, 'base-site'
        tmr['discovery'] = round(time.time() - _t0, 1)
    # карточка Яндекса (телефон/адрес/сайт) ценна даже когда собственный сайт не найден —
    # для 73% базы без сайта это готовый контакт для обзвона/рассылки.
    if card:
        r['card'] = card
    if not site:
        r['method'] = src
        # контакты из карточки Яндекса — С ПОДПИСЬЮ источника и ролью «общий» (владелец
        # 2026-07-23: карточный контакт = приёмная, ценность ниже ЛПР — так он и
        # ранжируется: роль без ЛПР-баллов, source виден продажнику в панели)
        if card.get('phone'):
            r['phones'] = [card['phone']]
            r['phones_source'] = 'serp-card:yandex'
        if card.get('email'):
            r['emails'] = [{'email': card['email'], 'role': 'общий', 'person': '',
                            'mx_ok': mx_ok(card['email']),
                            'source': 'serp-card:yandex',
                            'source_url': card.get('mapurl') or '',
                            'verified_by': 'card-name-match'}]
            r['best_for_outreach'] = card['email']
        # Я.КАРТЫ по mapurl из карточки (владелец 2026-07-23): страница организации в Картах
        # (JS) содержит полный набор — все телефоны, официальный сайт, иногда email. Рендерим
        # браузером; найденный там свой сайт вернёт компанию в основной пайплайн краула.
        if card.get('mapurl') and not r.get('best_for_outreach'):
            _mtxt, _mhtml = _org_page_probe(card['mapurl'])
            if _mtxt:
                _m_em = sorted({e.lower() for e in EMAIL_RE.findall(_mtxt)
                                if not e.lower().endswith(_IMG_EXT)})
                _m_ph = sorted(set(re.sub(r'[\s\-()]', '', p)
                                   for p in _PHONE_SITE.findall(_mtxt)))[:5]
                _m_site = ''
                for _uu in re.findall(r'https?://[^\s"\'<>]+', _mhtml):
                    if _is_own_site(_uu):
                        _m_site = _uu
                        break
                if _m_em:
                    r['emails'] = (r.get('emails') or []) + [
                        {'email': e, 'role': 'общий', 'person': '', 'mx_ok': mx_ok(e),
                         'source': 'maps:yandex', 'source_url': card['mapurl'],
                         'verified_by': 'card-name-match'} for e in _m_em[:3]]
                    r['best_for_outreach'] = r.get('best_for_outreach') or _m_em[0]
                if _m_ph and not r.get('phones'):
                    r['phones'] = _m_ph
                    r['phones_source'] = 'maps:yandex'
                if _m_site:
                    r['maps_site'] = _domain(_m_site)   # кандидат сайта для будущего краула
        # ЕГРЮЛ-email по ИНН (dadata findById, источник egrul:dadata - директива владельца)
        if not r.get('best_for_outreach') and company.get('inn'):
            _ege = _egrul_emails_by_inn(company['inn'])
            if _ege:
                r['emails'] = (r.get('emails') or []) + [
                    {'email': e, 'role': 'юрзначимый (ЕГРЮЛ)', 'person': '', 'mx_ok': mx_ok(e),
                     'source': 'egrul:dadata', 'source_url': '', 'verified_by': 'inn'}
                    for e in _ege]
                r['best_for_outreach'] = _ege[0]
        # VK-группа компании (владелец: «интересная идея, давай») - контакты с ролями
        if not _NO_VK_LOOKUP and not r.get('best_for_outreach'):
            try:
                vkc = find_vk_group_contacts(company)
            except Exception:  # noqa: BLE001
                vkc = None
            if vkc:
                r['vk_group'] = vkc
                if vkc.get('emails'):
                    r['emails'] = (r.get('emails') or []) + [
                        {'email': e, 'role': 'общий', 'person': '', 'mx_ok': mx_ok(e),
                         'source': 'vk-group', 'source_url': vkc['url'],
                         'verified_by': vkc['verified_by']} for e in vkc['emails']]
                    r['best_for_outreach'] = vkc['emails'][0]
                if vkc.get('phones') and not r.get('phones'):
                    r['phones'] = vkc['phones']
                    r['phones_source'] = 'vk-group'
        # #7: собственного сайта нет (хвост 78%) -> ищем контакты в бизнес-справочниках
        if not _NO_DIR_LOOKUP and not r.get('best_for_outreach'):
            try:
                dc = find_directory_contacts(company)
            except Exception:  # noqa: BLE001
                dc = None
            if dc:
                r['directory'] = dc
                _dirsrc = f'directory:{_domain(dc["dir_url"])}'
                if dc.get('emails'):
                    r['emails'] = [{'email': e, 'role': 'общий', 'person': '',
                                    'source_url': dc['dir_url'], 'source': _dirsrc,
                                    'verified_by': dc.get('verified_by')} for e in dc['emails']]
                    r['best_for_outreach'] = dc['emails'][0]
                if dc.get('phones') and not r.get('phones'):
                    r['phones'] = dc['phones']
                r['method'] = f'directory:{_domain(dc["dir_url"])}'
                return r
        r['error'] = f'сайт не найден ({src})' + (' [карточка Я есть]' if card else '')
        if _SMTP_CHECK:
            _finalize_smtp(r)
        return r
    if not site.startswith('http'):
        site = 'http://' + site
    r['site'] = _domain(site)
    r['site_source'] = src
    # ФАЗИРОВКА (владелец 2026-07-23): discovery_only = только НАЙТИ сайт (дёшево, чистый
    # xmlriver), краул/staff/провайдер — отдельной фазой позже по готовому списку сайтов.
    if _DISCOVERY_ONLY:
        r['method'] = 'discovery-only'
        return r
    time.sleep(_PACE(*pace))
    # поисковый этап: staff-страница компании через SERP (устойчив к вариациям URL).
    # Выключается флагом no_staff_search (для быстрых прогонов/экономии xmlriver-квоты).
    staff_urls = []
    if not _NO_STAFF_SEARCH:
        try:
            staff_urls = find_staff_via_search(company, _domain(site))
            if staff_urls:
                r['staff_search'] = staff_urls
        except Exception:  # noqa: BLE001
            pass
    _t0 = time.time()
    text, pages, err, csrc = crawl_contacts(site, pace, extra_pages=staff_urls)
    tmr['crawl'] = round(time.time() - _t0, 1)
    if csrc:
        r['contact_src'] = csrc   # разбор разметок: метод+local-part+контекст по каждому email
    if err:
        r['timings'] = tmr
        r['error'] = err
        return r
    if _RETURN_TEXT:
        r['crawled_text'] = text[:24000]  # для офлайн модель-сравнения экстрактора
    _t0 = time.time()
    if _SKIP_PROVIDER:
        # только краул+regex, без provider (быстрый сбор текстов для модель-теста)
        emails = sorted(set(e.lower() for e in EMAIL_RE.findall(text)
                            if not e.lower().endswith(('.png', '.jpg', '.gif', '.webp'))))
        data, how = {'emails': [{'email': e, 'role': 'общий', 'person': ''} for e in emails[:8]],
                     'phones': [], 'best_for_outreach': emails[0] if emails else ''}, 'regex-skip'
    else:
        data, how = extract_roles(text, company)
    tmr['provider'] = round(time.time() - _t0, 1)
    r['timings'] = tmr
    # --- верификация принадлежности сайта именно этой компании ---
    digits = re.sub(r'\D', '', text)
    inn = str(company.get('inn') or '')
    ogrn = str(company.get('ogrn') or '')
    verified = None
    if inn and re.search(r'\b' + re.escape(inn) + r'\b', text):
        verified = 'inn'                       # ИНН найден на сайте — жёсткое совпадение
    elif ogrn and ogrn in digits:
        verified = 'ogrn'
    else:
        # телефон из базы совпал с телефоном на сайте?
        base_phones = {re.sub(r'\D', '', p)[-10:] for p in (company.get('phones') or []) if p}
        site_phones = {re.sub(r'\D', '', p)[-10:] for p in _PHONE_SITE.findall(text)}
        if base_phones and (base_phones & site_phones):
            verified = 'phone'
        elif data.get('owner_match') is True:
            verified = 'provider'              # провайдер-судья подтвердил
        elif data.get('owner_match') is False:
            verified = 'mismatch'              # провайдер: сайт НЕ этой компании
    # конкурент по тексту сайта (сам производит компрессоры/насосы) — не для рассылки
    is_comp = bool(data.get('is_compressor_maker'))
    blocked = (verified == 'mismatch') or is_comp
    emails = data.get('emails', []) if not blocked else []
    _urlmap = (csrc or {}).get('emails', {})
    for e in emails:
        e['mx_ok'] = mx_ok(e.get('email', ''))
        # провенанс контакта: точная страница-источник + КАНАЛ (метод извлечения),
        # чтобы продажник видел «откуда» без сопоставления с contact_src.
        _es = _urlmap.get((e.get('email') or '').lower().strip()) or {}
        e['source_url'] = _es.get('url', '')
        # канал: staff-страница / сайт-контакты / главная / js-render — по URL и методу
        _u = (e['source_url'] or '').lower()
        if any(h in _u for h in _STAFF_HINTS):
            e['source'] = 'own-site:staff'
        elif _es.get('src') == 'js-render':
            e['source'] = 'own-site:js'
        else:
            e['source'] = 'own-site'
    r.update({'emails': emails, 'phones': data.get('phones', []),
              'best_for_outreach': data.get('best_for_outreach', '') if not blocked else '',
              'activity': data.get('activity', ''), 'is_competitor': is_comp,
              'pages_crawled': pages, 'extract': how, 'method': 'ok',
              'verified': verified, 'owner_reason': data.get('owner_reason', '')})
    if is_comp:
        r['error'] = 'конкурент (производит компрессоры/насосы — по тексту сайта)'
    elif verified == 'mismatch':
        r['error'] = 'сайт НЕ этой компании (провайдер-судья)'
    elif not emails:
        r['error'] = 'email на сайте не найдены'
    # ДОБОР для компаний С сайтом, но без найденного на нём email (владелец: обогащать
    # как можно полнее). Раньше эти доноры (ЕГРЮЛ/справочник) работали ТОЛЬКО в ветке
    # «сайт не найден» — компании с сайтом, но пустым краулом, бросались без контакта.
    if not blocked and not r.get('best_for_outreach') and company.get('inn'):
        try:
            _ege = _egrul_emails_by_inn(company['inn'])
        except Exception:  # noqa: BLE001
            _ege = None
        if _ege:
            r['emails'] = (r.get('emails') or []) + [
                {'email': e, 'role': 'юрзначимый (ЕГРЮЛ)', 'person': '', 'mx_ok': mx_ok(e),
                 'source': 'egrul:dadata', 'source_url': '', 'verified_by': 'inn'}
                for e in _ege]
            r['best_for_outreach'] = _ege[0]
            r.pop('error', None)
    if not blocked and not r.get('best_for_outreach') and not _NO_DIR_LOOKUP:
        try:
            dc = find_directory_contacts(company)
        except Exception:  # noqa: BLE001
            dc = None
        if dc and dc.get('emails'):
            r['directory'] = dc
            _dirsrc = f'directory:{_domain(dc["dir_url"])}'
            r['emails'] = (r.get('emails') or []) + [
                {'email': e, 'role': 'общий', 'person': '', 'source_url': dc['dir_url'],
                 'source': _dirsrc, 'verified_by': dc.get('verified_by')} for e in dc['emails']]
            r['best_for_outreach'] = dc['emails'][0]
            if dc.get('phones') and not r.get('phones'):
                r['phones'] = dc['phones']
                r['phones_source'] = _dirsrc
            r.pop('error', None)
    if _SMTP_CHECK:
        _finalize_smtp(r)
    return r


def _find_base():
    """Найти obzvon_all*.csv в storage дропа / известных местах."""
    import glob
    _d = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get('BASE_CSV', ''),
             os.path.join(os.environ.get('DROP_DIR', ''), 'obzvon_all_2026-07-16.csv')
             if os.environ.get('DROP_DIR') else '',
             r'C:\seostat\drop\drop-storage\obzvon_all_2026-07-16.csv',
             os.path.join(_d, 'drop-storage', 'obzvon_all_2026-07-16.csv')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    for root in (_d, os.path.dirname(_d), r'C:\sender'):
        try:
            hits = glob.glob(os.path.join(root, '**', 'obzvon_all*.csv'), recursive=True)
            if hits:
                return max(hits, key=os.path.getsize)
        except Exception:  # noqa: BLE001
            continue
    return None


def _get_base(name='obzvon_all_2026-07-16.csv'):
    """Локальный путь к базе; если не найден — скачать с дропа в кэш (канонический источник)."""
    p = _find_base()
    if p:
        return p
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.base_cache.csv')
    if os.path.exists(cache) and os.path.getsize(cache) > 100_000_000:
        return cache
    url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/' + name
    req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(req, timeout=900) as r, open(cache, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return cache if os.path.getsize(cache) > 100_000_000 else None


def _base_peek(n=3):
    import csv
    p = _get_base()
    if not p:
        return {'error': 'база не найдена (ни локально, ни на дропе)'}
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')
        header = next(rd, [])
        rows = [next(rd, []) for _ in range(n)]
    cols = [{'i': i, 'name': (header[i] if i < len(header) else ''),
             'samples': [r[i] if i < len(r) else '' for r in rows]} for i in range(len(header))]
    return {'path': p, 'ncols': len(header), 'columns': cols}


def _base_index(inn_set):
    """Один проход по базе → {ИНН: {name, site, city, phones}} для ИНН из inn_set. Нужен
    news_enrich: по новостной компании берём известный сайт [20] из базы (краулим его без
    xmlriver — эффективно), город из юрадреса [9], телефоны [18] для верификации сайта."""
    import csv
    p = _get_base()
    if not p or not inn_set:
        return {}
    INN, KRAT, POLN, ADDR, REG, PHONES, SITE = 1, 5, 6, 9, 10, 18, 20
    try:
        csv.field_size_limit(2 ** 18)
    except Exception:  # noqa: BLE001
        pass
    want = set(str(i) for i in inn_set)
    out = {}
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
            if len(row) <= SITE:
                continue
            inn = (row[INN] or '').strip()
            if inn not in want:
                continue
            addr = row[ADDR] or ''
            mc = re.search(r'(?:\bг\.\s*|\bгород\s+|\bпгт\.?\s*|\bп\.\s*|\bс\.\s*|\bсело\s+|'
                           r'\bдер\.\s*|\bд\.\s*|\bрп\.?\s*|\bстаница\s+)([А-ЯЁ][А-Яа-яЁё-]+)', addr)
            site = re.split(r'[ ,;|]+', (row[SITE] or '').strip())[0]
            out[inn] = {'name': (row[POLN] or row[KRAT] or '').strip(),
                        'site': site if site.startswith('http') else (f'http://{site}' if site else ''),
                        'city': (mc.group(1) if mc else '') or (row[REG] or '').strip(),
                        'phones': [x.strip() for x in (row[PHONES] or '').split('|') if x.strip()][:4]}
            if len(out) >= len(want):
                break
    return out


def _base_pick(no_site=True, size_col=None, limit=500, okved_prefixes=None):
    """csv.reader (правильно разбирает ';' ВНУТРИ кавычек — иначе колонка [32] «Найденные
    ОКВЭД» с ';' сдвигает выравнивание и выручку [34]), авто-раскавычивает имена.
    Фильтр (без сайта), ранжируем по size_col (выручка), топ-N."""
    import csv
    p = _get_base()
    if not p:
        return {'error': 'база не найдена'}
    INN, KRAT, POLN, ADDR, REG, DIRECTOR, OKVED, OKVED_ALL, PHONES, SITE = 1, 5, 6, 9, 10, 13, 16, 17, 18, 20
    if size_col is None:
        size_col = 34
    try:
        csv.field_size_limit(2 ** 18)  # 256КБ: легит-поля влезают, «сбежавшие» кавычки
        # быстро дают csv.Error (строка пропускается) вместо буферизации мегабайтов = не тормозим
    except Exception:  # noqa: BLE001
        pass
    picked = []
    scanned = 0
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')  # QUOTE_MINIMAL по умолчанию — корректно
        next(rd, None)  # header
        while True:
            try:
                row = next(rd)
            except StopIteration:
                break
            except Exception:  # noqa: BLE001
                continue  # битая строка — пропускаем, скан не рушим
            scanned += 1
            if len(row) <= size_col:
                continue
            site = (row[SITE] or '').strip()
            if no_site and site:
                continue
            if okved_prefixes and (row[OKVED] or '')[:2] not in okved_prefixes:
                continue
            try:
                sz = float(re.sub(r'[^\d.]', '', (row[size_col] or '0').replace(',', '.')) or 0)
            except Exception:  # noqa: BLE001
                sz = 0.0
            # ГОРОД из полного юрадреса [9] (в базе он точный, ЕГРЮЛ): «г. Чехов», «пгт Х»,
            # «с. Y» — точнее для xmlriver-поиска сайта, чем регион; фолбэк — регион [10].
            addr = (row[ADDR] or '') if len(row) > ADDR else ''
            mc = re.search(r'(?:\bг\.\s*|\bгород\s+|\bпгт\.?\s*|\bп\.\s*|\bс\.\s*|\bсело\s+|'
                           r'\bдер\.\s*|\bд\.\s*|\bрп\.?\s*|\bстаница\s+)([А-ЯЁ][А-Яа-яЁё-]+)', addr)
            city = (mc.group(1) if mc else '') or (row[REG] or '').strip()
            phones = [p.strip() for p in (row[PHONES] or '').split('|') if p.strip()] \
                if len(row) > PHONES else []
            picked.append((sz, {'inn': (row[INN] or '').strip(),
                                'name': (row[POLN] or row[KRAT] or '').strip(),
                                'city': city, 'region': (row[REG] or '').strip(),
                                'director': (row[DIRECTOR] or '').strip() if len(row) > DIRECTOR else '',
                                'phones': phones[:4],
                                'okved': (row[OKVED] or '').strip(),
                                'okved_all': (row[OKVED_ALL] or '').strip()[:600]
                                if len(row) > OKVED_ALL else '',
                                'site': (row[SITE] or '').strip(), 'size': sz}))
    picked.sort(key=lambda t: t[0], reverse=True)
    return {'path': p, 'scanned': scanned, 'total_no_site': len(picked),
            'companies': [c for _s, c in picked[:limit]]}


def _done_inns(dirpath):
    """Множество уже обработанных ИНН из ВСЕХ enrich_stream*.jsonl (резюмируемость массового
    прогона: при рестарте не перекрауливаем сделанное). jsonl устойчив к битым строкам.
    ПЕРЕПРОВЕРКА ПРОВАЙДЕР-ФЕЙЛОВ: запись extract='regex-provider-fail' (провайдер лежал) НЕ
    считается done, пока не набрано _PROVFAIL_CAP попыток → компания переобработается на
    следующих чанках цепочки (провайдер к тому времени ожил → получит роли)."""
    import glob
    _PROVFAIL_CAP = 3
    done = set()
    fails = {}
    for fp in glob.glob(os.path.join(dirpath, 'enrich_stream*.jsonl')):
        try:
            with open(fp, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    inn = str(rec.get('inn') or '')
                    if not inn:
                        continue
                    if rec.get('extract') == 'regex-provider-fail':
                        fails[inn] = fails.get(inn, 0) + 1   # копим попытки, пока НЕ done
                    else:
                        done.add(inn)                        # любой иной исход = done
        except Exception:  # noqa: BLE001
            pass
    for inn, c in fails.items():   # исчерпали лимит попыток → принимаем как есть (не зацикливаемся)
        if c >= _PROVFAIL_CAP:
            done.add(inn)
    return done


def _chain_next(args):
    """Самочейнинг серверного mass-прогона: пишем СЛЕДУЮЩИЙ подписанный job на дроп, чтобы
    раннер продолжил БЕЗ песочницы (она реапит фон-процессы). Пишем в НАЧАЛЕ обработки чанка
    (переживает таймаут раннера). Стоп-флаг НЕЗАВИСИМЫЙ по режиму: news_enrich → news_stop.flag,
    иначе mass_stop.flag (иначе новостное обогащение вставало бы вместе с массовым). Либо пустой
    пул (следующий чанк обработает 0 компаний → не зачейнит). done-set гарантирует отсутствие дублей."""
    import hmac as _h, hashlib as _hl
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    sec = os.environ.get('JOB_SECRET', '')
    stop_flag = 'news_stop.flag' if args.get('news_enrich') else 'mass_stop.flag'
    if not (drop and tok):
        return 'no-drop-env'
    try:
        req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tok})
        files = json.loads(urllib.request.urlopen(req, timeout=30).read())
        if any(f.get('name') == stop_flag for f in files):
            return 'stopped-by-flag'
    except Exception:  # noqa: BLE001
        pass
    jid = f'{int(time.time())}-chain{os.getpid()}'
    job = {'id': jid, 'task': 'enrich_contacts', 'args': args, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    if sec:
        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
    try:
        req = urllib.request.Request(drop + f'/job-{jid}.json',
                                     data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                                     method='PUT', headers={'X-Drop-Token': tok})
        urllib.request.urlopen(req, timeout=60)
        return jid
    except Exception as e:  # noqa: BLE001
        return f'chain-err:{str(e)[:60]}'


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    if args.get('op') == 'dolphin_conn1':
        # ЧИСТЫЙ тест: РОВНО один старт профиля + connect + открыть страницу (без повторных стартов).
        import browser_probe as BP
        import json as _j
        from playwright.sync_api import sync_playwright
        tokd = _read_secret('DOLPHIN_TOKEN')
        pid = str((args.get('dolphin_profiles') or ['?'])[0])
        _opd = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        r = {'op': 'dolphin_conn1', 'profile': pid}
        try:
            rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/browser_profiles/{pid}/start?automation=1',
                                        headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
            sd = _j.loads(_opd.open(rq, timeout=30).read())
            au = sd.get('automation') or {}
            r['start'] = sd.get('success'); port = au.get('port'); ws = au.get('wsEndpoint') or ''
            cdp = f'ws://127.0.0.1:{port}{ws}' if ws else f'http://127.0.0.1:{port}'
            r['port'] = port
            with sync_playwright() as pw:
                br = pw.chromium.connect_over_cdp(cdp, timeout=35000)
                ctx = br.contexts[0] if br.contexts else br.new_context()
                # сколько вкладок профиль ПРИТАЩИЛ из прошлой сессии (доказательство фикса
                # dolphin_close_tabs: после чистого стопа тут должно быть 0-1 about:blank)
                r['tabs_at_connect'] = sum(len(c.pages) for c in br.contexts)
                pg = ctx.new_page()
                pg.goto('https://example.com', timeout=30000, wait_until='domcontentloaded')
                r['connect'] = 'OK'; r['title'] = (pg.title() or '')[:50]
                BP.dolphin_close_tabs(br)
                try:
                    br.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            b = ''
            try:
                b = e.read().decode('utf-8', 'replace')[:150]
            except Exception:  # noqa: BLE001
                pass
            r['error'] = str(e).splitlines()[0][:100] + (f' | {b}' if b else '')
        finally:
            try:
                BP.dolphin_stop(pid, token=tokd)
            except Exception:  # noqa: BLE001
                pass
        json.dump(r, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_diag':
        # ДИАГНОСТИКА дельфина: list -> start (headless И обычный) -> connect_over_cdp (30с).
        # Пинпоинтит, где рвётся: API / старт профиля / рендер браузера (headless на серверах без GUI).
        import browser_probe as BP
        from playwright.sync_api import sync_playwright
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = [str(x) for x in (args.get('dolphin_profiles') or [])]
        listed = []
        try:
            listed = BP.dolphin_list(tokd)
        except Exception as e:  # noqa: BLE001
            listed = [{'err': str(e)[:80]}]
        if not profs:
            profs = [p['id'] for p in listed if p.get('id')]
        if not profs:  # токен протух (401) -> кэш dolphin-profiles.txt
            profs = _cached_dolphin_profiles()
        pid = profs[0] if profs else None
        res = {'op': 'dolphin_diag', 'token_present': bool(tokd),
               'list_count': len([x for x in listed if x.get('id')]),
               'list_raw': str(listed)[:200], 'profile_tested': pid, 'modes': {}}
        # сырое тело 500 со старта + сырой ответ list (точная причина от Dolphin)
        _opd = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for label, path in (('start', f'browser_profiles/{pid}/start?automation=1'),
                            ('list', 'browser_profiles?limit=100')):
            try:
                rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/{path}',
                                            headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
                body = _opd.open(rq, timeout=30).read().decode('utf-8', 'replace')
                res[f'raw_{label}'] = body[:280]
            except Exception as e:  # noqa: BLE001
                b = ''
                try:
                    b = e.read().decode('utf-8', 'replace')[:280]
                except Exception:  # noqa: BLE001
                    pass
                res[f'raw_{label}'] = f'{str(e)[:60]} | body: {b}'
        # РЕШАЮЩИЙ ТЕСТ: сырой старт (БЕЗ stop-first) -> connect_over_cdp -> открыть страницу
        try:
            import json as _j
            rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/browser_profiles/{pid}/start?automation=1',
                                        headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
            sd = _j.loads(_opd.open(rq, timeout=30).read())
            au = sd.get('automation') or {}
            port = au.get('port'); ws = au.get('wsEndpoint') or ''
            cdp = f'ws://127.0.0.1:{port}{ws}' if ws else f'http://127.0.0.1:{port}'
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                br = pw.chromium.connect_over_cdp(cdp, timeout=35000)
                ctx = br.contexts[0] if br.contexts else br.new_context()
                pg = ctx.new_page()
                pg.goto('https://example.com', timeout=30000, wait_until='domcontentloaded')
                res['e2e'] = {'connect': 'OK', 'title': (pg.title() or '')[:50], 'port': port}
                BP.dolphin_close_tabs(br)
                try:
                    br.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            res['e2e'] = {'connect': 'FAIL', 'err': str(e).splitlines()[0][:120]}
        finally:
            try:
                BP.dolphin_stop(pid, token=tokd)
            except Exception:  # noqa: BLE001
                pass
        for hl in (True, False):
            r = {}
            try:
                cdp, port = BP.dolphin_start(pid, headless=hl, token=tokd)
                r['start_ok'] = True; r['port'] = port; r['cdp'] = str(cdp)[:70]
                with sync_playwright() as p:
                    try:
                        b = p.chromium.connect_over_cdp(cdp, timeout=30000)
                        r['cdp_connect'] = 'OK'; r['contexts'] = len(b.contexts)
                        BP.dolphin_close_tabs(b)
                        try:
                            b.close()
                        except Exception:  # noqa: BLE001
                            pass
                    except Exception as e:  # noqa: BLE001
                        r['cdp_connect'] = 'FAIL: ' + str(e).splitlines()[0][:90]
            except Exception as e:  # noqa: BLE001
                r['start_ok'] = False; r['err'] = str(e)[:140]
            finally:
                try:
                    BP.dolphin_stop(pid, token=tokd)
                except Exception:  # noqa: BLE001
                    pass
            res['modes']['headless' if hl else 'gui'] = r
        json.dump(res, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_batch':
        # БОЕВОЙ ОПО-прогон: N профилей ПАРАЛЛЕЛЬНО, каждый в ОДНОЙ сессии гонит свою пачку
        # компаний (goto по каждой, капча решается по ходу через handle_captcha), в конце stop.
        # Вход: companies [{ogrn,inn,name,sector,...}], dolphin_profiles [id...]. Выход -> csv на дроп.
        import multiprocessing as _mp
        tokd = _read_secret('DOLPHIN_TOKEN')
        profiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        comps = args.get('companies') or []
        if not profiles or not comps:
            json.dump({'op': 'opo_batch', 'error': 'нужны dolphin_profiles и companies'}, sys.stdout, ensure_ascii=False)
            return
        nprof = min(len(profiles), int(args.get('max_profiles', 20)))
        profiles = profiles[:nprof]
        # разложить компании по профилям (round-robin)
        buckets = [[] for _ in range(nprof)]
        for i, c in enumerate(comps):
            buckets[i % nprof].append(c)
        # каждый профиль — ОТДЕЛЬНЫЙ ПРОЦЕСС (Playwright sync не потокобезопасен, паттерн dolphin_pool)
        _d = os.path.dirname(os.path.abspath(__file__))
        # разнос по времени (наводка владельца: 20 разом = профили не успевают прогрузиться
        # + rate-limit чеко): старт профилей каскадом раз в stagger_sec, пауза между
        # компаниями внутри сессии sleep_ms (+джиттер).
        stag = float(args.get('stagger_sec', 5))
        slp = int(args.get('sleep_ms', 2000))
        procs, outs = [], []
        for i in range(nprof):
            outp = os.path.join(_d, f'.opo_out_{i}.json')
            outs.append(outp)
            pr = _mp.Process(target=_opo_worker,
                             args=(profiles[i], tokd, buckets[i], outp, slp, i * stag))
            pr.start(); procs.append(pr)
        for pr in procs:
            pr.join(timeout=int(args.get('total_timeout', 1500)))
        results = {}
        for outp in outs:
            try:
                results.update(json.load(open(outp, encoding='utf-8')))
                os.remove(outp)
            except Exception:  # noqa: BLE001
                pass
        # выгрузка csv на дроп
        import io as _io2
        import csv as _csvb
        buf = _io2.StringIO(); w = _csvb.writer(buf, delimiter=';')
        w.writerow(['ogrn', 'inn', 'name', 'sector', 'rtn_opo', 'pressure_equip', 'lic_nums',
                    'captcha', 'blocked', 'error'])
        n_opo = 0; n_press = 0
        for ogrn, r in results.items():
            if r.get('rtn_opo'):
                n_opo += 1
            if r.get('pressure_equip'):
                n_press += 1
            w.writerow([ogrn, r.get('inn', ''), r.get('name', ''), r.get('sector', ''),
                        r.get('rtn_opo', ''), r.get('pressure_equip', ''),
                        '|'.join(r.get('lic_nums', []) or []),
                        r.get('captcha', '') or '', r.get('blocked', ''), r.get('error', '')])
        try:
            _D3 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tk = os.environ.get('DROP_TOKEN', '')
            fn = args.get('out_file', 'checko-opo.csv')
            _D3.open(urllib.request.Request(drop + '/' + fn, data=buf.getvalue().encode('utf-8'),
                     method='PUT', headers={'X-Drop-Token': tk}), timeout=90)
            uploaded = fn
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:70]}'
        errs = sum(1 for r in results.values() if r.get('error'))
        blk = sum(1 for r in results.values() if r.get('blocked'))
        json.dump({'op': 'opo_batch', 'profiles_used': nprof, 'companies': len(comps),
                   'processed': len(results), 'with_rtn_opo': n_opo,
                   'with_pressure_equip': n_press, 'errors': errs, 'blocked': blk,
                   'uploaded': uploaded,
                   'sample_pressure': [{'name': r.get('name'), 'lic': r.get('lic_nums')}
                                       for r in results.values() if r.get('pressure_equip')][:5],
                   'sample_opo': [{'name': r.get('name'), 'lic': r.get('lic_nums')}
                                  for r in results.values() if r.get('rtn_opo')][:5]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_licenses':
        # ОПО через ЛИЦЕНЗИИ Ростехнадзора на checko: /company/{OGRN}/licenses/data?source=07
        # (наводка владельца). Дельфин-профили автоподтяжкой по токену. Возвращает per-OGRN
        # маркеры + сырой сниппет первой для верификации парсера.
        import browser_probe as BP
        _dtoken = _read_secret('DOLPHIN_TOKEN')
        _dprofiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _dtoken)
        # маркеры лицензии Ростехнадзора на эксплуатацию ОПО
        RTN = re.compile(r'взрывопожароопасн|химически\s+опасн|эксплуатац\w+\s+\w*\s*опасн|'
                         r'Ростехнадзор|горн\w+\s+работ|I,?\s*II\b.*класс\w*\s+опасн', re.I)
        PRESSURE = re.compile(r'давлени\w*\s+более\s+0[.,]07|нагрева\s+воды\s+более\s+115|'
                              r'оборудован\w*,?\s*работающ\w*\s+под\s+давлением|'
                              r'сосуд\w*,?\s*работающ\w*\s+под\s+давлением|под\s+давлением\s+более', re.I)
        LIC_NUM = re.compile(r'№?\s*[А-Я]{1,3}-?\d{2}-\d{5,6}|ВХ-\d{2}-\d{5,6}', re.I)
        out = {}; first_snip = None
        for i, c in enumerate(args.get('companies') or []):
            ogrn = str(c.get('ogrn') or '').strip()
            if not ogrn:
                out[c.get('inn', '?')] = {'error': 'нет OGRN'}; continue
            url = f'https://checko.ru/company/{ogrn}/licenses/data?source=07'
            try:
                pargs = {'url': url, 'solve': True, 'return_html': True,
                         'html_cap': 200000, 'wait_ms': 9000, 'screenshot': False}
                if _dprofiles and _dtoken:
                    pargs.update(dolphin_profile=str(_dprofiles[i % len(_dprofiles)]), dolphin_token=_dtoken)
                pr = BP.probe(pargs)
                html = pr.get('html', '') or ''
                txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I))
                txt = re.sub(r'\s+', ' ', txt)
                has = bool(RTN.search(txt))
                out[ogrn] = {'inn': c.get('inn'), 'name': (c.get('name') or '')[:40],
                             'rtn_license': has, 'pressure_equip': bool(PRESSURE.search(txt)),
                             'lic_nums': list(set(LIC_NUM.findall(txt)))[:4],
                             'blocked': _looks_blocked(html), 'captcha': pr.get('captcha_type'),
                             'html_len': len(html)}
                if first_snip is None and html:
                    first_snip = txt[:600]
            except Exception as e:  # noqa: BLE001
                out[ogrn] = {'error': str(e)[:100]}
        json.dump({'op': 'opo_licenses', 'dolphin_profiles': len(_dprofiles),
                   'results': out, 'first_snippet': first_snip}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'base_header':
        import csv as _csv
        p = _get_base()
        if not p:
            json.dump({'error': 'база не найдена'}, sys.stdout, ensure_ascii=False); return
        try:
            _csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csv.reader(f, delimiter=';')
            hdr = next(rd, [])
            sample = next(rd, [])
        cols = [{'i': i, 'name': (h or '')[:40], 'sample': (sample[i] if i < len(sample) else '')[:50]}
                for i, h in enumerate(hdr)]
        json.dump({'op': 'base_header', 'path': p, 'ncols': len(hdr), 'columns': cols},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') in ('centrifugal_inns', 'centrifugal_export'):
        # ОКВЭД-воронка центробежных компрессоров из обзвон-базы (уже checko+) -> ГОТОВАЯ
        # выгрузка с контактами и выручкой на дроп. Матч по основному [16] И доп. [17] ОКВЭД.
        import csv as _csv
        import io as _io
        # ПОРОГ ВЫРУЧКИ СВОЙ ПО ОТРАСЛЯМ (изучено по исследованию центробежников):
        # ядро=машины гарантированно; чем крупнее типовой парк, тем выше порог (режем шум).
        # Спец-исключения: промгазы (спецы мельче, но ЦБК точно есть) — низкий порог;
        # водоканалы/очистные — порог 0 (решает инвестпрограмма/концессия, не выручка).
        # code -> (floor_₽, sector, tier). Матч по префиксу кода в основном+доп ОКВЭД.
        SECTOR = {
            # --- ЯДРО ---
            '06.10': (3e9, 'добыча нефти', 'core'),
            '06.20': (3e9, 'добыча газа', 'core'),
            '49.50.21': (2e9, 'транспорт газа', 'core'),
            '49.50.11': (2e9, 'транспорт нефти', 'core'),
            '52.10.22': (1e9, 'хранение газа (ПХГ)', 'core'),
            '19.20': (3e9, 'НПЗ/нефтепродукты', 'core'),
            '19.10': (2e9, 'кокс', 'core'),
            '20.14': (1.5e9, 'орг.химия/нефтехимия', 'core'),
            '20.16': (1.5e9, 'пластмассы', 'core'),
            '20.17': (1.5e9, 'синт.каучук', 'core'),
            '20.15': (1.5e9, 'удобрения/аммиак', 'core'),
            '20.11': (0.4e9, 'промышленные газы', 'core'),   # спецы мельче, машины точно есть
            '24.10': (2e9, 'чёрная металлургия', 'core'),
            # --- ВТОРОЙ КОНТУР ---
            '20.13': (1.5e9, 'неорг.химия', 'second'),
            '24.42': (2e9, 'алюминий', 'second'),
            '24.43': (2e9, 'свинец-цинк-олово', 'second'),
            '24.44': (2e9, 'медь', 'second'),
            '24.45': (2e9, 'цветмет проч.', 'second'),
            '05.10': (2e9, 'уголь', 'second'),
            '07.10': (2e9, 'ГОК железорудный', 'second'),
            '07.29': (2e9, 'ГОК цветной', 'second'),
            '35.11': (1.5e9, 'энергетика (генерация)', 'second'),
            '35.30': (1e9, 'пар/горячая вода', 'second'),
            '37.00': (0.1e9, 'очистные/сточные', 'water'),   # владелец: водоканалы от 100 млн
            '36.00': (0.1e9, 'водоканал', 'water'),          # владелец: водоканалы от 100 млн
            '17.11': (2e9, 'ЦБК (целлюлоза)', 'second'),
            '23.51': (1.5e9, 'цемент', 'second'),
            '10.81': (1e9, 'сахар', 'second'),
            '09.10': (1e9, 'нефтесервис', 'second'),
        }
        include_second = args.get('include_second', True)
        codes = tuple(c for c, (_f, _s, t) in SECTOR.items() if include_second or t != 'second')
        floor_mult = float(args.get('floor_mult', 1.0) or 1.0)   # множитель порогов (ужесточить/смягчить)
        p = _get_base()
        if not p:
            json.dump({'op': 'centrifugal_export', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        (INN, OGRN, KRAT, POLN, ADDR, REG, OKVED, OKVED_ALL, PHONES, EMAILS, SITES,
         PHONES_S, EMAIL_S, PRIORITY, EQUIP, REV_NUM) = (1, 2, 5, 6, 9, 10, 16, 17, 18, 19, 20, 21, 22, 28, 30, 34)
        try:
            _csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        seen = set(); picked = []
        by_tier = {'core': 0, 'second': 0, 'water': 0}
        by_sector = {}
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csv.reader(f, delimiter=';')
            next(rd, None)
            while True:
                try:
                    row = next(rd)
                except StopIteration:
                    break
                except Exception:  # noqa: BLE001
                    continue
                if len(row) <= REV_NUM:
                    continue
                inn = (row[INN] or '').strip()
                if not inn or inn in seen:
                    continue
                hay = (row[OKVED] or '') + ' ' + (row[OKVED_ALL] or '')
                matched = [c for c in codes if c in hay]
                if not matched:
                    continue
                try:
                    rev = float(re.sub(r'[^\d.]', '', (row[REV_NUM] or '0')) or 0)
                except Exception:  # noqa: BLE001
                    rev = 0.0
                if rev <= 0:
                    continue   # владелец: компании без выручки пока не интересны
                # проходит, если по ЛЮБОЙ из отраслей-матчей выручка >= её порога (× floor_mult).
                # Отрасль лида = та, по которой прошёл с наименьшим порогом (самая релевантная/мягкая).
                ok = None
                for c in matched:
                    fl, sec, tr = SECTOR[c]
                    if rev >= fl * floor_mult:
                        if ok is None or (fl * floor_mult) < ok[0]:
                            ok = (fl * floor_mult, sec, tr, c)
                if ok is None:
                    continue
                _fl, sector, tier, _code = ok
                seen.add(inn)
                emails = ((row[EMAILS] or '') + ' | ' + (row[EMAIL_S] or '')).strip(' |')
                phones = ((row[PHONES] or '') + ' | ' + (row[PHONES_S] or '')).strip(' |')
                picked.append({
                    'inn': inn, 'ogrn': (row[OGRN] or '').strip(),
                    'name': (row[POLN] or row[KRAT] or '').strip(),
                    'region': (row[REG] or '').strip(), 'okved_main': (row[OKVED] or '').strip(),
                    'revenue_rub': rev, 'tier': tier, 'sector': sector,
                    'phones': phones, 'emails': emails, 'site': (row[SITES] or '').strip(),
                    'priority': (row[PRIORITY] or '').strip(), 'equipment': (row[EQUIP] or '').strip()[:120],
                })
                by_tier[tier] = by_tier.get(tier, 0) + 1
                by_sector[sector] = by_sector.get(sector, 0) + 1
        # сортировка: сначала ядро/вода, потом по выручке (вода без выручки — вверх по инвест-приоритету)
        picked.sort(key=lambda x: (0 if x['tier'] in ('core', 'water') else 1, -x['revenue_rub']))
        # CSV на дроп
        buf = _io.StringIO()
        w = _csv.writer(buf, delimiter=';')
        w.writerow(['inn', 'ogrn', 'name', 'region', 'okved_main', 'revenue_rub', 'tier', 'sector',
                    'phones', 'emails', 'site', 'priority_score', 'equipment'])
        for r0 in picked:
            w.writerow([r0['inn'], r0['ogrn'], r0['name'], r0['region'], r0['okved_main'],
                        int(r0['revenue_rub']), r0['tier'], r0['sector'], r0['phones'], r0['emails'],
                        r0['site'], r0['priority'], r0['equipment']])
        blob = buf.getvalue().encode('utf-8')
        with_email = sum(1 for r0 in picked if '@' in (r0['emails'] or ''))
        try:
            _D2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
            _D2.open(urllib.request.Request(drop + '/centrifugal-base.csv', data=blob,
                     method='PUT', headers={'X-Drop-Token': tok}), timeout=120)
            uploaded = True
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:80]}'
        json.dump({'op': 'centrifugal_export', 'total': len(picked), 'with_email': with_email,
                   'by_tier': by_tier, 'by_sector': dict(sorted(by_sector.items(), key=lambda x: -x[1])),
                   'floor_mult': floor_mult, 'uploaded': uploaded, 'file': 'centrifugal-base.csv',
                   'top5': [{'inn': r0['inn'], 'name': r0['name'][:40],
                             'rev_млрд': round(r0['revenue_rub'] / 1e9, 1),
                             'email': (r0['emails'][:40] if r0['emails'] else '')} for r0 in picked[:5]]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_serp':
        # ТЕСТ: достаточно ли СНИППЕТОВ xmlriver для ОПО-данных (без браузера/дельфина)?
        u2, k2 = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
        out = {}
        for c in (args.get('companies') or []):
            inn = str(c.get('inn') or ''); name = c.get('name', '')
            q = f'{name} ИНН {inn} опасный производственный объект компрессорная станция реестр ОПО checko nadzor-info'
            su = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(u2)
                  + '&key=' + urllib.parse.quote(k2) + '&domain=ru&query=' + urllib.parse.quote(q))
            try:
                xml = _DIRECT.open(su, timeout=35).read().decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                out[name] = {'error': str(e)[:80]}; continue
            snips = ' '.join(re.findall(r'<(?:passages|title|text|content)>(.*?)</(?:passages|title|text|content)>', xml, re.S))
            snips = re.sub(r'<[^>]+>', ' ', snips)
            obj = _OPO_OBJ.findall(snips)
            reg = re.findall(r'А\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?', snips)
            ctx = bool(re.search(r'опасн\w+\s+производствен|ОПО|Ростехнадзор|промышленн\w+\s+безопасн', snips, re.I))
            out[name] = {'inn_in_snips': inn in snips.replace(' ', ''),
                         'opo_ctx': ctx, 'opo_objects': list(set(obj))[:5],
                         'opo_regs': list(set(reg))[:5], 'snip_sample': snips[:400]}
        json.dump({'op': 'opo_serp', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_probe':
        # РАЗВЕДКА авторитетного источника ОПО по ИНН: checko/list-org (раздел ОПО из
        # Ростехнадзора) + офиц. реестр через SERP. Браузер+CapMonster, дельфин если есть профиль.
        # Самодостаточно (локальные переменные) — не трогаем модульные глобали.
        import browser_probe as BP
        _dtoken = _read_secret('DOLPHIN_TOKEN')
        # порядок: args -> live-список по токену -> кэш dolphin-profiles.txt (устойчиво к 401)
        _dprofiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _dtoken)
        inn = str(args.get('inn') or '')
        name = args.get('name', '')
        # eo.nadzor-info.ru — профильный портал по ОПО/промбезопасности (владелец 2026-07-23)
        cands = [f'https://eo.nadzor-info.ru/search?q={inn}',
                 f'https://checko.ru/company/{inn}',
                 f'https://www.rusprofile.ru/search?query={inn}',
                 f'https://www.list-org.com/search?type=inn&val={inn}']
        # найдём офиц.-реестр/агрегатор через SERP
        try:
            u2, k2 = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
            if u2 and k2:
                q = f'{name} ИНН {inn} опасный производственный объект реестр ОПО'
                su = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(u2)
                      + '&key=' + urllib.parse.quote(k2) + '&domain=ru&query=' + urllib.parse.quote(q))
                xml = _DIRECT.open(su, timeout=35).read().decode('utf-8', 'replace')
                for uu in re.findall(r'<url>(.*?)</url>', xml, re.S)[:5]:
                    uu = uu.strip().replace('&amp;', '&')
                    if uu not in cands:
                        cands.append(uu)
        except Exception:  # noqa: BLE001
            pass
        results = {}
        for _i, url in enumerate(cands[:6]):
            try:
                pargs = {'url': url, 'solve': True, 'return_html': True,
                         'html_cap': 220000, 'wait_ms': 9000, 'screenshot': False}
                if _dprofiles and _dtoken:
                    pargs.update(dolphin_profile=str(_dprofiles[_i % len(_dprofiles)]),
                                 dolphin_token=_dtoken)
                out = BP.probe(pargs)
                html = out.get('html', '') or ''
                txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ',
                                                     html, flags=re.S | re.I))
                low = txt.lower()
                results[url] = {
                    'html_len': len(html), 'blocked': _looks_blocked(html),
                    'captcha': out.get('captcha_type'),
                    'has_opo_word': ('опасн' in low and 'производствен' in low),
                    'opo_regs': list(set(re.findall(r'А\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?', txt)))[:6],
                    'opo_objects': list(set(_OPO_OBJ.findall(txt)))[:5],
                    'inn_present': inn in txt.replace(' ', ''),
                }
            except Exception as e:  # noqa: BLE001
                results[url] = {'error': str(e)[:120]}
        json.dump({'op': 'opo_probe', 'inn': inn, 'dolphin_profiles_found': len(_dprofiles),
                   'results': results}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dnscheck':
        # проверка DNS доменов с РФ-IP сервера: A + HTTP-редирект + почтовые записи
        # (MX/SPF/DKIM/DMARC через nslookup — питон-сокет TXT/MX не умеет).
        import socket as _sock
        import subprocess as _sp
        import urllib.request as _u
        RESOLVER = args.get('resolver', '8.8.8.8')
        # DKIM-селекторы под провайдеров: Я360=mail, Mail.ru=mailru, VK=dkim/selector
        DKIM_SEL = args.get('dkim_selectors') or ['mail', 'mailru', 'dkim', 'default', 'selector1']

        def _nslookup(qtype, name):
            try:
                r = _sp.run(['nslookup', '-type=' + qtype, name, RESOLVER],
                            capture_output=True, text=True, timeout=20,
                            encoding='utf-8', errors='replace')
                return (r.stdout or '') + (r.stderr or '')
            except Exception as e:  # noqa: BLE001
                return f'__err__ {e}'

        out = {}
        for dom in (args.get('domains') or []):
            rec = {'a': None, 'http_code': None, 'http_redirect': None,
                   'mx': None, 'spf': None, 'dmarc': None, 'dkim_selector': None}
            try:
                rec['a'] = _sock.gethostbyname(dom)
            except Exception:  # noqa: BLE001
                rec['a'] = None
            for scheme in ('https', 'http'):
                try:
                    req = _u.Request(f'{scheme}://{dom}/', method='GET',
                                     headers={'User-Agent': 'Mozilla/5.0'})
                    class _NoRedir(_u.HTTPRedirectHandler):
                        def redirect_request(self, *a, **k):
                            return None
                    r = _u.build_opener(_NoRedir).open(req, timeout=15)
                    rec['http_code'] = r.getcode()
                    break
                except _u.HTTPError as e:
                    rec['http_code'] = e.code
                    rec['http_redirect'] = e.headers.get('Location')
                    break
                except Exception:  # noqa: BLE001
                    continue
            # MX
            mxo = _nslookup('MX', dom)
            mxs = re.findall(r'mail exchanger\s*=\s*(\S+)', mxo)
            rec['mx'] = mxs[0].rstrip('.') if mxs else None
            # SPF (TXT на корне)
            txto = _nslookup('TXT', dom)
            spf = re.search(r'"(v=spf1[^"]*)"', txto)
            rec['spf'] = spf.group(1) if spf else None
            # DMARC
            dmo = _nslookup('TXT', '_dmarc.' + dom)
            dm = re.search(r'"(v=DMARC1[^"]*)"', dmo)
            rec['dmarc'] = dm.group(1) if dm else None
            # DKIM: пробуем селекторы, фиксируем первый найденный
            for sel in DKIM_SEL:
                dko = _nslookup('TXT', f'{sel}._domainkey.{dom}')
                if re.search(r'v=DKIM1|k=rsa|p=[A-Za-z0-9+/]{20,}', dko):
                    rec['dkim_selector'] = sel
                    break
            out[dom] = rec
        json.dump({'op': 'dnscheck', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hh_vacancy_scan':
        # ВАКАНСИЯ->КОМПАНИЯ (инверсия владельца): API hh закрыт целиком (forbidden), но
        # ЧЕЛОВЕЧЕСКИЙ сайт hh.ru/search/vacancy открыт -> парсим ЕГО через дельфин.
        # Ищем компрессорные вакансии по РФ -> работодатели -> кандидаты в горячие лиды.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        queries = args.get('queries') or ['машинист компрессорных установок',
                                          'оператор компрессорной станции',
                                          'машинист воздуходувных установок']
        pages = int(args.get('pages', 1))
        found = {}   # employer -> {vacancies:[...], area}
        raw_diag = {}
        for q in queries[:6]:
            for pg in range(pages):
                url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
                       + '&items_on_page=50&page=' + str(pg))
                try:
                    r = BP.probe({'url': url, 'return_html': True, 'html_cap': 400000,
                                  'wait_ms': 4000, 'screenshot': False, 'solve': True,
                                  'dolphin_profile': pid, 'dolphin_token': tokd})
                    html = r.get('html') or ''
                    if q not in raw_diag:
                        raw_diag[q] = {'html_len': len(html), 'captcha': r.get('captcha_type'),
                                       'has_serp': 'vacancy-serp' in html or 'vacancy-card' in html,
                                       'forbidden': 'forbidden' in html[:2000].lower()}
                    # карточки: работодатель (data-qa vacancy-serp__vacancy-employer /
                    # vacancy-card__company-name) + заголовок вакансии
                    emps = re.findall(r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>([^<]{2,80})<', html)
                    titles = re.findall(r'data-qa="[^"]*vacancy[^"]*title[^"]*"[^>]*>([^<]{3,120})<', html)
                    for i, emp in enumerate(emps):
                        emp = re.sub(r'\s+', ' ', emp).strip()
                        if not emp:
                            continue
                        rec = found.setdefault(emp, {'query': q, 'titles': []})
                        if i < len(titles):
                            rec['titles'].append(re.sub(r'\s+', ' ', titles[i]).strip()[:80])
                except Exception as e:  # noqa: BLE001
                    raw_diag[q] = {'error': f'{type(e).__name__}: {str(e)[:70]}'}
        try:
            BP.dolphin_stop(pid, token=tokd)
        except Exception:  # noqa: BLE001
            pass
        out = {'op': 'hh_vacancy_scan', 'profile': pid, 'employers_found': len(found),
               'diag': raw_diag,
               'sample': [{'employer': e, 'query': v['query'], 'titles': v['titles'][:2]}
                          for e, v in list(found.items())[:15]]}
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'vk_oauth_dolphin':
        # Добить VK через дельфин (владелец): открыть OAuth-URL ВНУТРИ дельфин-профиля ->
        # токен привяжется к IP профиля (socks5). Затем ТЕМ ЖЕ профилем дёрнуть groups.search,
        # чтобы IP совпал. Шаг 1 (probe_ip): сравнить исходящий IP профиля и сервера.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        out = {'op': 'vk_oauth_dolphin', 'profile': pid}
        if not pid:
            out['error'] = 'нет профиля'; json.dump(out, sys.stdout, ensure_ascii=False); return
        # IP сервера (прямой) и IP через дельфин-профиль
        try:
            out['server_ip'] = _DIRECT.open('https://api.ipify.org', timeout=15).read().decode()
        except Exception as e:  # noqa: BLE001
            out['server_ip'] = f'err:{str(e)[:40]}'
        try:
            r = BP.probe({'url': 'https://api.ipify.org', 'return_html': True, 'wait_ms': 2500,
                          'screenshot': False, 'dolphin_profile': pid, 'dolphin_token': tokd})
            body = re.sub(r'<[^>]+>', ' ', r.get('html') or '') + ' ' + (r.get('text') or '')
            m = re.search(r'\d+\.\d+\.\d+\.\d+', body)
            out['dolphin_ip'] = m.group(0) if m else ('пусто:' + body[:80])
        except Exception as e:  # noqa: BLE001
            out['dolphin_ip'] = f'err:{str(e)[:60]}'
        out['ip_match'] = (out.get('server_ip') == out.get('dolphin_ip'))
        # если IP разные - groups.search с сервера всё равно упрётся; если совпали ИЛИ
        # если дёргать API тем же профилем - сработает. Даём URL для ручного OAuth в профиле:
        _cid = args.get('client_id', '54687645')
        out['oauth_url'] = (f'https://oauth.vk.com/authorize?client_id={_cid}&scope=groups'
                            '&redirect_uri=https://oauth.vk.com/blank.html&response_type=token&v=5.199')
        # проба: если передан vk_token - дёрнуть groups.search ЧЕРЕЗ дельфин-профиль
        vt = args.get('vk_token') or _read_secret('VK_TOKEN_USER')
        if vt and args.get('try_search'):
            # через новую retry-функцию (перебор профилей, общий IP) + СЫРОЙ дамп
            raw = _vk_api_via_dolphin('groups.search', {'q': 'Северсталь', 'count': 3}, vt)
            out['vk_raw'] = json.dumps(raw, ensure_ascii=False)[:400]
            if 'response' in raw:
                out['search_via_dolphin'] = 'OK: ' + str(len((raw.get('response') or {}).get('items') or [])) + ' групп'
            elif raw.get('error'):
                out['search_via_dolphin'] = 'VK-ошибка: ' + str(raw['error'].get('error_msg', ''))[:80]
            else:
                out['search_via_dolphin'] = 'пусто (дельфин не отдал JSON - профили 500?)'
        try:
            BP.dolphin_stop(pid, token=tokd)
        except Exception:  # noqa: BLE001
            pass
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'coverage_probe':
        # ЧИСТЫЙ замер на выборке: обогащаем companies со ВСЕМИ источниками, считаем разбивку
        # ИЗ РЕЗУЛЬТАТА (не из БД - без легаси-мусора). write_db=false по умолчанию.
        import collections as _coll
        globals()['_ZAKUPKI_CHECK'] = bool(args.get('zakupki_check', True))
        globals()['_SMTP_CHECK'] = bool(args.get('smtp_check', True))
        globals()['_NO_VK_LOOKUP'] = bool(args.get('no_vk_lookup', True))  # VK токен без прав
        pace = (float(args.get('pace_min', 1.5)), float(args.get('pace_max', 3.5)))
        comps = args.get('companies') or []
        # ПАРАЛЛЕЛЬНО (последовательно 20 не влезали в таймаут 1800с). Инициализируем семафоры
        # (op-путь минует main-настройку). browser/xmlriver ограничены семафорами внутри.
        bw = max(1, min(int(args.get('browser_workers', 4)), 12))
        globals()['_SEM_BROWSER'] = threading.Semaphore(bw)
        _cw = max(1, min(int(args.get('workers', 8)), 16))
        def _one(c):
            try:
                return enrich_one(c, pace)
            except Exception as e:  # noqa: BLE001
                return {'inn': c.get('inn'), 'error': f'exc:{str(e)[:60]}'}
        with ThreadPoolExecutor(max_workers=_cw) as _ex:
            res = list(_ex.map(_one, comps))
        n = len(res)
        with_site = sum(1 for r in res if r.get('site'))
        with_email = sum(1 for r in res if r.get('emails'))
        with_best = sum(1 for r in res if r.get('best_for_outreach'))
        with_phone = sum(1 for r in res if r.get('phones'))
        verified = sum(1 for r in res if r.get('verified') in ('inn', 'ogrn', 'phone', 'provider'))
        src = _coll.Counter(); smtp = _coll.Counter(); roles = _coll.Counter()
        for r in res:
            seen = set()
            for e in (r.get('emails') or []):
                b = (e.get('source') or 'unknown').split(':')[0]
                if b not in seen:
                    src[b] += 1; seen.add(b)
                if e.get('smtp'):
                    smtp[e['smtp']] += 1
                rl = (e.get('role') or '').split('(')[0].strip()[:20]
                if rl:
                    roles[rl] += 1
        # примеры лучших контактов
        sample = [{'name': (r.get('name') or '')[:30], 'best': r.get('best_for_outreach'),
                   'site': r.get('site'), 'n_emails': len(r.get('emails') or [])}
                  for r in res if r.get('best_for_outreach')][:8]
        json.dump({'op': 'coverage_probe', 'total': n, 'with_site': with_site,
                   'with_any_email': with_email, 'with_best_email': with_best,
                   'with_phone': with_phone, 'verified': verified,
                   'email_sources': dict(src), 'smtp_status': dict(smtp),
                   'top_roles': dict(roles.most_common(8)), 'sample': sample},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'tail_stream':
        # Хвост любого jsonl на сервере (мониторинг реальных данных прогона). args: file, n.
        _dirt = os.path.dirname(os.path.abspath(__file__))
        fn = args.get('file', 'enrich_core.jsonl')
        fp = fn if os.path.isabs(fn) else os.path.join(_dirt, fn)
        n = int(args.get('n', 10))
        rows = []; total = 0
        try:
            with open(fp, encoding='utf-8') as f:
                lines = f.readlines()
            total = len(lines)
            for ln in lines[-n:]:
                try:
                    j = json.loads(ln)
                    # компактный вид: главное для проверки «реально ли собирается»
                    rows.append({'inn': j.get('inn'), 'name': (j.get('name') or '')[:34],
                                 'site': j.get('site'), 'site_source': j.get('site_source'),
                                 'best': j.get('best_for_outreach'),
                                 'n_emails': len(j.get('emails') or []),
                                 'email_sample': [(e.get('email'), e.get('source'), e.get('smtp'))
                                                  for e in (j.get('emails') or [])[:3]],
                                 'phones': (j.get('phones') or [])[:2],
                                 'verified': j.get('verified'), 'method': j.get('method'),
                                 'opo': j.get('opo'), 'zakupki': bool(j.get('zakupki')),
                                 'error': j.get('error')})
                except Exception:  # noqa: BLE001
                    rows.append({'raw_broken': ln[:80]})
        except FileNotFoundError:
            json.dump({'op': 'tail_stream', 'error': f'нет файла {fp}'}, sys.stdout, ensure_ascii=False)
            return
        # агрегат по всему файлу
        agg = {'total': total, 'with_site': 0, 'with_email': 0, 'with_best': 0, 'src': {}}
        try:
            with open(fp, encoding='utf-8') as f:
                for ln in f:
                    try:
                        j = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if j.get('site'): agg['with_site'] += 1
                    if j.get('emails'): agg['with_email'] += 1
                    if j.get('best_for_outreach'): agg['with_best'] += 1
                    for e in (j.get('emails') or []):
                        b = (e.get('source') or '?').split(':')[0]
                        agg['src'][b] = agg['src'].get(b, 0) + 1
        except Exception:  # noqa: BLE001
            pass
        json.dump({'op': 'tail_stream', 'file': fn, 'aggregate': agg, 'tail': rows},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'export_core':
        # ФИНАЛЬНАЯ ВЫГРУЗКА ядра с провенансом (для продажников). Источник — jsonl-поток
        # прогона (там smtp/source/opo/zakupki, чего нет в компактной БД). Лучшая запись на ИНН,
        # мердж отрасли/выручки из core-info, ПОСТ-ФИЛЬТР ОПО (юр-справки → не сигнал), скоринг.
        import csv as _csv
        import io as _io
        import glob as _g
        _dirx = os.path.dirname(os.path.abspath(__file__))
        stream = args.get('stream_file', 'enrich_core2.jsonl')
        # инфо по ядру (sector/revenue) из core396.json если есть
        info = {}
        try:
            for c in json.load(open(os.path.join(_dirx, args.get('info_file', 'core396.json')), encoding='utf-8')):
                info[str(c.get('inn'))] = c
        except Exception:  # noqa: BLE001
            pass
        LAW_REF = ('sudact.ru/law', 'consultant.ru', 'garant.ru', 'cntd.ru', 'kodeks',
                   'pravo.gov', 'normativ', 'zakonbase', 'legalacts', '/law/', 'zakonrf')
        def _score(rec):
            s = 0
            if rec.get('best_for_outreach'): s += 3
            if rec.get('verified') in ('inn', 'ogrn', 'phone'): s += 2
            if any((e.get('person') or '').strip() for e in (rec.get('emails') or [])): s += 2
            if rec.get('_opo_ok'): s += 2
            if rec.get('zakupki'): s += 1
            if rec.get('phones'): s += 1
            try:
                s += min(3, int(float(info.get(str(rec.get('inn')), {}).get('revenue_rub') or 0) / 5e9))
            except Exception:  # noqa: BLE001
                pass
            return s
        best = {}
        for fp in _g.glob(os.path.join(_dirx, stream.rsplit('.', 1)[0] + '*.jsonl')):
            try:
                for ln in open(fp, encoding='utf-8'):
                    try:
                        j = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    inn = str(j.get('inn') or '')
                    if not inn:
                        continue
                    # ОПО пост-фильтр: юр-справка в source_url → не считаем сигналом
                    op = j.get('opo')
                    j['_opo_ok'] = bool(op and isinstance(op, dict) and op.get('opo')
                                        and not any(l in (op.get('source_url') or '').lower() for l in LAW_REF))
                    prev = best.get(inn)
                    # лучшая запись: с best_for_outreach > больше email > есть сайт
                    key = (bool(j.get('best_for_outreach')), len(j.get('emails') or []), bool(j.get('site')))
                    if prev is None or key > prev['_k']:
                        j['_k'] = key
                        best[inn] = j
            except Exception:  # noqa: BLE001
                pass
        # опционально ограничить списком ИНН (ядро)
        want = set(str(i) for i in (args.get('inns') or []))
        rows = [best[i] for i in best if not want or i in want]
        rows.sort(key=lambda r: -_score(r))
        buf = _io.StringIO()
        w = _csv.writer(buf, delimiter=';')
        w.writerow(['score', 'inn', 'name', 'sector', 'revenue_rub', 'site', 'site_source',
                    'best_email', 'best_smtp', 'verified', 'all_contacts(email|role|source|smtp)',
                    'phones', 'opo', 'opo_object', 'opo_source', 'zakupki_contact', 'method', 'error'])
        n_best = n_person = n_opo = 0
        for r in rows:
            inn = str(r.get('inn') or '')
            ci = info.get(inn, {})
            ems = r.get('emails') or []
            best_email = r.get('best_for_outreach') or ''
            best_smtp = next((e.get('smtp') for e in ems if e.get('email') == best_email), '')
            all_c = ' ; '.join(f"{e.get('email')}|{(e.get('role') or '')}|{e.get('source') or ''}|{e.get('smtp') or ''}"
                               for e in ems)
            op = r.get('opo') if isinstance(r.get('opo'), dict) else {}
            zk = r.get('zakupki') or {}
            zkc = ''
            if isinstance(zk, dict):
                c0 = next((c for c in (zk.get('cards') or []) if c.get('contact_person')), None) or {}
                if c0:
                    zkc = f"{c0.get('contact_person','')}|{c0.get('email','')}|{c0.get('phone','')}"
            if best_email: n_best += 1
            if any((e.get('person') or '').strip() for e in ems): n_person += 1
            if r.get('_opo_ok'): n_opo += 1
            w.writerow([_score(r), inn, (r.get('name') or ci.get('name') or ''),
                        ci.get('sector', ''), ci.get('revenue_rub', ''),
                        r.get('site') or '', r.get('site_source') or '',
                        best_email, best_smtp, r.get('verified') or '', all_c,
                        ' '.join(r.get('phones') or []),
                        'да' if r.get('_opo_ok') else '', op.get('opo_object', '') if r.get('_opo_ok') else '',
                        op.get('source_url', '') if r.get('_opo_ok') else '', zkc,
                        r.get('method') or '', r.get('error') or ''])
        blob = buf.getvalue().encode('utf-8')
        out_name = args.get('out', 'centrifugal-core-enriched.csv')
        uploaded = False
        try:
            _D3 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
            _D3.open(urllib.request.Request(drop + '/' + out_name, data=blob, method='PUT',
                     headers={'X-Drop-Token': tok}), timeout=120)
            uploaded = True
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:80]}'
        json.dump({'op': 'export_core', 'rows': len(rows), 'with_best': n_best,
                   'with_person_email': n_person, 'with_opo': n_opo, 'file': out_name,
                   'uploaded': uploaded}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'source_selftest':
        # ЕДИНЫЙ ТЕСТ каждого источника отдельно (владелец: каждое обогащение запускается
        # отдельно и даёт данные). На реальных компаниях -> per-source pass/данные.
        import time as _t
        test_inn_site = args.get('test_company') or {'inn': '7830000426', 'name': 'Водоканал Санкт-Петербурга',
                                                     'city': 'Санкт-Петербург'}
        priv = {'inn': '7725104641', 'name': 'ДОРОЖНО-СТРОИТЕЛЬНАЯ КОМПАНИЯ АВТОБАН', 'ogrn': '1027739058258'}
        out = {}
        def _run(name, fn):
            t0 = _t.time()
            try:
                r = fn()
                out[name] = {'ok': bool(r), 'sec': round(_t.time() - t0, 1),
                             'sample': (json.dumps(r, ensure_ascii=False)[:220] if r else None)}
            except Exception as e:  # noqa: BLE001
                out[name] = {'ok': False, 'err': f'{type(e).__name__}: {str(e)[:80]}'}

        def _run_panel(name, fn, candidates):
            # источник, доступность данных у которого зависит от компании: пробегаем небольшую
            # панель реальных компаний, источник считается рабочим если ХОТЬ ОДНА дала данные.
            t0 = _t.time(); hits = 0; sample = None; err = None
            for c in candidates:
                try:
                    r = fn(c)
                    if r:
                        hits += 1
                        if sample is None:
                            sample = json.dumps(r, ensure_ascii=False)[:220]
                except Exception as e:  # noqa: BLE001
                    err = f'{type(e).__name__}: {str(e)[:60]}'
            out[name] = {'ok': hits > 0, 'sec': round(_t.time() - t0, 1),
                         'hits': f'{hits}/{len(candidates)}', 'sample': sample}
            if err:
                out[name]['err'] = err
        # 1. xmlriver сайт+карточка
        _run('1_xmlriver_site', lambda: (lambda t: {'site': t[0], 'src': t[1],
             'card_phone': (t[2] or {}).get('phone')})(find_site_via_xmlriver(test_inn_site)))
        # 2. staff-поиск (панель: [name, domain]) — данные есть только если у компании есть
        #    страница руководства; проверяем на нескольких, source рабочий если хоть одна дала.
        staff_panel = args.get('staff_panel') or [
            {'name': 'ПАО Северсталь', 'domain': 'severstal.com'},
            {'name': 'ПАО НЛМК', 'domain': 'nlmk.ru'},
            {'name': 'ПАО ММК', 'domain': 'mmk.ru'},
            {'name': 'ЕвроХим', 'domain': 'eurochem.ru'},
        ]
        _run_panel('2_staff_search',
                   lambda c: find_staff_via_search({'name': c['name']}, c['domain']),
                   staff_panel)
        # 3. ЕГРЮЛ-email (панель ИНН) — email в ЕГРЮЛ есть далеко не у всех; пробегаем панель
        #    реальных ИНН, source рабочий если хоть один вернул зарегистрированный email.
        egrul_panel = args.get('egrul_panel') or [test_inn_site['inn'], priv['inn'],
                                                  '7830000426', '7736050003', '7728168971']
        _run_panel('3_egrul_email', lambda inn: _egrul_emails_by_inn(inn), egrul_panel)
        # 4. ЕИС-закупки
        _run('4_zakupki_eis', lambda: (lambda z: {'rss_items': (z or {}).get('rss_items'),
             'cards': len((z or {}).get('cards') or []),
             'first_contact': next((c for c in (z or {}).get('cards') or [] if c.get('contact_person')), None)}
             )(find_zakupki_contacts(test_inn_site['inn'], max_cards=2)))
        # 5. справочники
        _run('5_directory', lambda: find_directory_contacts(priv))
        # 6. SMTP-проба
        _run('6_smtp_verify', lambda: {'support@yandex.ru': smtp_verify('support@yandex.ru'),
             'nonexist999zzz@yandex.ru': smtp_verify('nonexist999zzz@yandex.ru')})
        # 7. ОПО-сигнал
        _run('7_opo_signal', lambda: find_opo_signal(priv))
        # 8. dadata резолв
        _run('8_dadata_resolve', lambda: __import__('news_scan').dadata_suggest('Северстали', _read_secret('DADATA_TOKEN')))
        json.dump({'op': 'source_selftest', 'sources': out,
                   'ok_count': sum(1 for v in out.values() if v.get('ok')),
                   'total': len(out)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'coverage_report':
        # Замер покрытия по списку ИНН из enrich.db (без повторного обогащения): у скольких
        # сайт/email/по каким источникам/smtp-статус/verified. Читает то, что уже накоплено.
        import enrich_db as EDB
        import collections as _coll
        db = EDB.EnrichDB()
        inns = [str(i) for i in (args.get('inns') or [])]
        if not inns:
            inns = [r[0] for r in db.cx.execute('SELECT inn FROM companies').fetchall()]
        st = {'total': len(inns), 'with_site': 0, 'with_any_email': 0, 'with_best': 0,
              'verified': 0, 'by_email_source': {}, 'by_smtp': {}, 'with_phone': 0}
        src_c = _coll.Counter(); smtp_c = _coll.Counter()
        for inn in inns:
            c = db.cx.execute('SELECT site,best_email,verified,phones FROM companies WHERE inn=?',
                              (inn,)).fetchone()
            if not c:
                continue
            site, best, ver, phones = c
            if site:
                st['with_site'] += 1
            if best:
                st['with_best'] += 1
            if ver in ('inn', 'ogrn', 'phone', 'provider'):
                st['verified'] += 1
            if phones:
                st['with_phone'] += 1
            ems = db.cx.execute('SELECT email,source,mx_ok FROM emails WHERE inn=?', (inn,)).fetchall()
            if ems:
                st['with_any_email'] += 1
            seen_src = set()
            for em, esrc, mxok in ems:
                base = (esrc or 'unknown').split(':')[0]
                if base not in seen_src:
                    src_c[base] += 1; seen_src.add(base)
        st['by_email_source'] = dict(src_c)
        json.dump({'op': 'coverage_report', **st}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'clean_bad_sites':
        # Вычистить из enrich.db «сайты», попавшие из контент-платформ/агрегаторов (dzen-
        # инцидент): site -> NULL, чтобы переобогащение пошло заново. dry_run=true - отчёт.
        import enrich_db as EDB
        db = EDB.EnrichDB()
        bad = ('dzen.', 'zen.yandex', 'vc.ru', 'tenchat', 'pikabu', 'habr', 'rutube', 'youla',
               'journal.tinkoff', 'dprom.online', 'vbr.ru', '2gis', 'zoon', 'yandex.',
               'google.', 'youtube', 'wikipedia', 'avito', 'hh.ru', 'rusprofile', 'list-org',
               'checko', 'zachestnyibiznes', 'rbc.ru')
        rows = db.cx.execute("SELECT inn, site FROM companies WHERE site!='' AND site IS NOT NULL").fetchall()
        hit = [(i, st) for i, st in rows if any(b in str(st).lower() for b in bad)]
        out = {'op': 'clean_bad_sites', 'dry_run': bool(args.get('dry_run', True)),
               'total_with_site': len(rows), 'bad_found': len(hit), 'sample': hit[:15]}
        if not args.get('dry_run', True):
            for i, _st in hit:
                db.cx.execute("UPDATE companies SET site='' WHERE inn=?", (i,))
            db.cx.commit()
            out['cleaned'] = len(hit)
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'smtp_verify':
        # тест SMTP-пробы: emails -> статус (и проверка, открыт ли порт 25 с сервера)
        out = []
        for e in (args.get('emails') or [])[:12]:
            st = smtp_verify(e)
            out.append({'email': e, 'mx_ok': mx_ok(e), 'smtp': st})
            time.sleep(1.5)   # пауза между доменами (антиспам)
        json.dump({'op': 'smtp_verify', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_set_proxies':
        # Раскидать прокси по профилям через Remote API (облачный - работает даже если локальное
        # приложение лежит). Список: args.proxies ИЛИ dolphin-proxies.txt с дропа. По одному
        # прокси на профиль (round-robin). Формат прокси: user:pass@host:port (схема scheme, деф socks5).
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        # список прокси
        raw_px = args.get('proxies')
        if not raw_px:
            try:
                _d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                url = os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt'
                req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
                raw_px = _d.open(req, timeout=30).read().decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                json.dump({'op': 'dolphin_set_proxies', 'error': f'нет списка прокси: {str(e)[:60]}'},
                          sys.stdout, ensure_ascii=False); return
        scheme = args.get('scheme', 'socks5')
        proxies = []
        for line in (raw_px if isinstance(raw_px, list) else raw_px.splitlines()):
            line = str(line).strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'(?:(socks5|socks4|https?)://)?(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', line)
            if not m:
                continue
            sc, user, pw, host, port = m.groups()
            px = {'type': sc or scheme, 'host': host, 'port': int(port)}
            if user:
                px['login'] = user; px['password'] = pw or ''
            proxies.append(px)
        if not (profs and proxies):
            json.dump({'op': 'dolphin_set_proxies', 'error': 'нет профилей или прокси',
                       'n_profiles': len(profs), 'n_proxies': len(proxies)},
                      sys.stdout, ensure_ascii=False); return
        # VK-профиль исключаем: его IP не меняем (токен VK к нему привязан, владелец 2026-07-23)
        vk_pin = str(args.get('vk_profile', _VK_PIN_PROFILE))
        skip_vk = bool(args.get('skip_vk_profile', True))
        results = []
        _pi = 0
        for pid in profs:
            if skip_vk and str(pid) == vk_pin:
                results.append({'profile': pid, 'proxy': 'SKIP (VK-профиль, IP не меняем)', 'ok': True})
                continue
            px = proxies[_pi % len(proxies)]; _pi += 1
            try:
                r = BP._dolphin_remote('PATCH', f'/browser_profiles/{pid}', {'proxy': px}, token=tokd)
                ok = bool(isinstance(r, dict) and (r.get('success') or r.get('data') or not r.get('error')))
                results.append({'profile': pid, 'proxy': f"{px['host']}:{px['port']}", 'ok': ok,
                                'resp': json.dumps(r, ensure_ascii=False)[:120]})
            except Exception as e:  # noqa: BLE001
                results.append({'profile': pid, 'proxy': f"{px['host']}:{px['port']}",
                                'ok': False, 'err': str(e)[:80]})
        json.dump({'op': 'dolphin_set_proxies', 'assigned': len(results),
                   'ok_count': sum(1 for r in results if r.get('ok')),
                   'proxies_available': len(proxies), 'results': results[:25]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_stop_all':
        # Погасить ВСЕ профили (сироты после прерванных прогонов) - dolphin_stop идемпотентен
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        done = []
        for pid in profs:
            try:
                BP.dolphin_stop(pid, token=tokd)
                done.append(pid)
            except Exception:  # noqa: BLE001
                pass
        json.dump({'op': 'dolphin_stop_all', 'stopped': done, 'count': len(done)},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'etp_probe':
        # проверка доступности коммерческих ЭТП с сервера (РФ-IP): отдаётся ли поиск/карточка
        # без логина. Владелец: «надо проверить так ли это».
        import ssl as _ssl
        _ctx = _ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = _ssl.CERT_NONE
        _op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                          urllib.request.HTTPSHandler(context=_ctx))
        urls = args.get('urls') or ['https://www.b2b-center.ru/market/',
                                    'https://www.fabrikant.ru/trades/', 'https://etprf.ru/']
        out = []
        for u in urls:
            rec = {'url': u}
            try:
                r = _op.open(urllib.request.Request(u, headers={'User-Agent': VC.UA}), timeout=25)
                html = r.read().decode('utf-8', 'replace'); low = html.lower()
                rec['status'] = r.status; rec['len'] = len(html)
                rec['markers'] = [k for k in ('войти', 'регистрац', 'личный кабинет', 'закупк',
                                              'тендер', 'контакт', 'организатор', 'телефон')
                                  if k in low]
            except urllib.error.HTTPError as e:
                rec['status'] = e.code
            except Exception as e:  # noqa: BLE001
                rec['error'] = f'{type(e).__name__}: {str(e)[:90]}'
            out.append(rec)
        json.dump({'op': 'etp_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'fsa_probe':
        # Разведка реестра аттестованных Ростехнадзора (pub.fsa.gov.ru) С СЕРВЕРА (РФ-IP +
        # Russian Trusted CA). Пробуем набор эндпоинтов/фильтров по тестовому ИНН, отчёт
        # статус+первые байты - понять форму API до написания парсера.
        test_inn = str(args.get('inn') or '4205000908')
        tries = [
            ('POST', 'https://pub.fsa.gov.ru/api/v1/rpa/common/certificates/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('POST', 'https://pub.fsa.gov.ru/api/v1/rpa/common/experts/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('POST', 'https://pub.fsa.gov.ru/api/v1/ral/common/experts/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('GET', 'https://pub.fsa.gov.ru/api/v1/rpa/common/dictionary/ affiliate'.replace(' ', ''), None),
        ]
        out = []
        for method, u, body in tries:
            rec = {'method': method, 'url': u}
            try:
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(u, data=data, method=method,
                    headers={'User-Agent': VC.UA, 'Content-Type': 'application/json',
                             'Accept': 'application/json'})
                r = _eis_get.__self__ if False else None  # noqa
                import ssl as _ssl
                _ctx = _ssl.create_default_context(); _ctx.check_hostname = False
                _ctx.verify_mode = _ssl.CERT_NONE
                _op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                  urllib.request.HTTPSHandler(context=_ctx))
                resp = _op.open(req, timeout=25)
                raw = resp.read()
                rec['status'] = resp.status
                rec['len'] = len(raw)
                rec['body_head'] = raw[:500].decode('utf-8', 'replace')
            except urllib.error.HTTPError as e:
                rec['status'] = e.code
                rec['body_head'] = e.read()[:300].decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                rec['error'] = f'{type(e).__name__}: {str(e)[:120]}'
            out.append(rec)
        json.dump({'op': 'fsa_probe', 'inn': test_inn, 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'mark_shared_phones':
        # Телефоны, встречающиеся у >=min_share компаний базы = «возможно общий» (бизнес-центр/
        # бухгалтерия/аутсорс). Владелец 2026-07-23: пометить, чтобы не считать прямым контактом.
        # Выход: shared_phones.txt на дроп (нормализованные 10-значные) + опц. флаг shared_phone
        # у компаний enrich.db. Email по телефонам НЕ переносим (отменено владельцем).
        import csv as _csvs
        try:
            _csvs.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'mark_shared_phones', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        PH = 18
        phone_inns = {}
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvs.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[1].strip()
                    if not inn:
                        continue
                    for _p in (row[PH] or '').split('|'):
                        dg = re.sub(r'\D', '', _p)
                        if len(dg) >= 10:
                            phone_inns.setdefault(dg[-10:], set()).add(inn)
                except Exception:  # noqa: BLE001
                    continue
        min_share = int(args.get('min_share', 3))
        shared = {ph: len(inns) for ph, inns in phone_inns.items() if len(inns) >= min_share}
        shared_inns = set()
        for ph, inns in phone_inns.items():
            if len(inns) >= min_share:
                shared_inns |= inns
        # список общих телефонов на дроп (для скоринга/отправки: членство = низкое доверие)
        uploaded = ''
        try:
            _D = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tk = os.environ.get('DROP_TOKEN', '')
            blob = '\n'.join(sorted(shared)).encode('utf-8')
            _D.open(urllib.request.Request(drop + '/shared_phones.txt', data=blob, method='PUT',
                    headers={'X-Drop-Token': tk}), timeout=90)
            uploaded = 'shared_phones.txt'
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:60]}'
        # флаг в enrich.db (только для уже присутствующих компаний)
        marked = 0
        if not args.get('dry_run', True):
            try:
                import enrich_db as EDB
                db = EDB.EnrichDB()
                try:
                    db.cx.execute('ALTER TABLE companies ADD COLUMN shared_phone INTEGER DEFAULT 0')
                    db.cx.commit()
                except Exception:  # noqa: BLE001
                    pass
                have = {r[0] for r in db.cx.execute('SELECT inn FROM companies').fetchall()}
                for inn in (shared_inns & have):
                    db.cx.execute('UPDATE companies SET shared_phone=1 WHERE inn=?', (inn,))
                    marked += 1
                db.cx.commit()
            except Exception as e:  # noqa: BLE001
                marked = f'db-err:{str(e)[:60]}'
        top = sorted(shared.items(), key=lambda x: -x[1])[:8]
        json.dump({'op': 'mark_shared_phones', 'dry_run': bool(args.get('dry_run', True)),
                   'min_share': min_share, 'shared_phones': len(shared),
                   'companies_on_shared_phones': len(shared_inns),
                   'uploaded': uploaded, 'marked_in_db': marked,
                   'top_shared': [{'phone': p, 'companies': n} for p, n in top]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'phone_match':
        # Перенос email внутри групп ОДИНАКОВЫХ телефонов базы 161к (владелец 2026-07-23:
        # «попробуем, посмотрим результат, с возможностью откатить»). dry_run=true (деф.) -
        # только отчёт без записи. Запись: emails с source='phone-match:<ИНН-донора>' ->
        # откат одним DELETE (op phone_match_rollback). Группы крупнее max_group (вирт.АТС/
        # колл-центры) пропускаются - там номер ничего не значит.
        import csv as _csvp
        try:
            _csvp.field_size_limit(2 ** 20)   # иначе строка с большим полем ломает ридер -> 0 строк
        except Exception:  # noqa: BLE001
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'phone_match', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        _diag = {'path': bp, 'size': os.path.getsize(bp)}
        with open(bp, encoding='utf-8-sig', newline='') as _f:
            _h0 = _f.readline()
            _r1 = _f.readline()
        _diag['header_first120'] = _h0[:120]
        _diag['sep_semicolon'] = _h0.count(';')
        _diag['sep_comma'] = _h0.count(',')
        _diag['sep_tab'] = _h0.count(chr(9))
        _diag['row1_first120'] = _r1[:120]
        if args.get('diag_only'):
            with open(bp, encoding='utf-8-sig', newline='') as _f2:
                _rd2 = _csvp.reader(_f2, delimiter=';')
                _hdr = next(_rd2, [])
                _diag['ncols'] = len(_hdr)
                _diag['col18_name'] = _hdr[18] if len(_hdr) > 18 else '?'
                _diag['col19_name'] = _hdr[19] if len(_hdr) > 19 else '?'
                _samp = []
                for _k in range(3):
                    _rw = next(_rd2, [])
                    _samp.append({'ncol': len(_rw), 'c18': (_rw[18] if len(_rw) > 18 else '')[:40],
                                  'c19': (_rw[19] if len(_rw) > 19 else '')[:40]})
                _diag['rows'] = _samp
            json.dump({'op': 'phone_match', 'diag': _diag}, sys.stdout, ensure_ascii=False)
            return
        INN_, NAME_, PH, EM = 1, 5, 18, 19
        groups = {}
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvp.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[INN_].strip()
                    if not inn:
                        continue
                    # телефоны отформатированы (+7 916 217-95-01) -> нормализуем ДО извлечения
                    phones = set()
                    for _p in (row[PH] or '').split('|'):
                        _dg = re.sub(r'\D', '', _p)
                        if len(_dg) >= 10:
                            phones.add(_dg[-10:])
                    ems = [e.lower() for e in re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', row[EM] or '')]
                    for ph in phones:
                        groups.setdefault(ph, []).append((inn, ems, (row[NAME_] or '')[:50]))
                except Exception:  # noqa: BLE001
                    continue
        _tot_rows = sum(len(m) for m in groups.values())
        _with_email = sum(1 for m in groups.values() for (i, e, n) in m if e)
        max_group = int(args.get('max_group', 6))       # крупные группы = БЦ/бухгалтерия, режем
        name_gate = bool(args.get('name_gate', True))   # общий бренд-токен обязателен (деф.)
        cand = []
        for ph, members in groups.items():
            if len(members) < 2 or len(members) > max_group:
                continue
            donors = [(i, e, n) for i, e, n in members if e]
            empty = [(i, e, n) for i, e, n in members if not e]
            if not donors or not empty:
                continue
            d_inn, d_em, d_nm = donors[0]
            _STOP = {'торг','групп','компан','сервис','строй','инвест','пром','рус','юг',
                     'снаб','плюс','центр','групп','альянс','капитал','холдинг','финанс'}
            def _toks(x):
                return {t for t in re.findall(r'[а-яёa-z]{4,}', (x or '').lower()) if t not in _STOP}
            for r_inn, _e, r_nm in empty:
                shared = _toks(d_nm) & _toks(r_nm)
                if name_gate and not shared:
                    continue   # нет общего бренд-токена -> вероятно БЦ/бухгалтерия, не холдинг
                cand.append({'inn': r_inn, 'email': d_em[0], 'donor': d_inn, 'phone': ph,
                             'to_name': r_nm, 'donor_name': d_nm,
                             'shared_token': sorted(shared)[:2]})
        import collections as _coll
        _size_hist = dict(_coll.Counter(min(len(m), 11) for m in groups.values() if len(m) >= 2))
        # примеры групп размера 6-10 (подозрительные: БЦ/бухгалтерия, не холдинг)
        _big_ex = []
        for ph, m in groups.items():
            if 6 <= len(m) <= 10 and any(e for i, e, n in m) and len(_big_ex) < 4:
                _big_ex.append({'phone': ph, 'names': [n[:32] for i, e, n in m]})
        _gsizes = sorted((len(m) for m in groups.values()), reverse=True)[:5]
        out = {'op': 'phone_match', 'dry_run': bool(args.get('dry_run', True)),
               'rows_with_phone': _tot_rows, 'unique_phones': len(groups),
               'rows_with_email_in_groups': _with_email,
               'biggest_groups': _gsizes,
               'groups_2_to_max': sum(1 for m in groups.values() if 2 <= len(m) <= max_group),
               'size_hist_2plus': _size_hist, 'big_group_examples': _big_ex,
               'candidates': len(cand), 'sample': cand[:12]}
        if not args.get('dry_run', True):
            import enrich_db as EDB
            db = EDB.EnrichDB()
            n = 0
            for c in cand:
                try:
                    db.add_email(c['inn'], c['email'], role='общий (phone-match)',
                                 source=f"phone-match:{c['donor']}", source_url='')
                    n += 1
                except Exception:  # noqa: BLE001
                    pass
            out['written'] = n
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'phone_match_rollback':
        # ОТКАТ phone-match одним DELETE (обещание владельцу)
        import enrich_db as EDB
        db = EDB.EnrichDB()
        cur = db.cx.execute("DELETE FROM emails WHERE source LIKE 'phone-match%'")
        db.cx.commit()
        json.dump({'op': 'phone_match_rollback', 'deleted': cur.rowcount}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'zakupki_mass':
        # МАССОВЫЙ ЕИС-проход (владелец: «не только 396, а ВСЕ компании, сверху вниз по
        # выручке» - параллельный слой скоринга). Контакты закупщиков (source zakupki:eis,
        # роль «закупки», ФИО из карточки) + ГОРЯЧИЙ сигнал, если предмет закупки - наше
        # оборудование. Дурабельно: .zk_done.txt по ИНН + zakupki_stream.jsonl; самочейн;
        # стоп - файл zakupki_stop.flag на дропе.
        import csv as _csvz
        try:
            _csvz.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        _dirz = os.path.dirname(os.path.abspath(__file__))
        done_p = os.path.join(_dirz, '.zk_done.txt')
        done = set()
        try:
            done = set(l.strip() for l in open(done_p, encoding='utf-8') if l.strip())
        except FileNotFoundError:
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'zakupki_mass', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        rows = []
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvz.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[1].strip()
                    if not inn or inn in done:
                        continue
                    rev = float(row[34] or 0)
                    rows.append((rev, inn, (row[5] or row[6] or '')[:60]))
                except Exception:  # noqa: BLE001
                    continue
        rows.sort(key=lambda x: -x[0])
        cap = int(args.get('cap', 120))
        chunk = rows[:cap]
        ZK_HOT = re.compile(r'компрессор|воздуходув|осушит|сжат\w*\s+воздух|пневмо|'
                            r'генератор\w*\s+(азот|кислород)|фотосепаратор|рентген\w*\s+инспек', re.I)
        db = None
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
        except Exception:  # noqa: BLE001
            pass
        st = {'processed': 0, 'with_contacts': 0, 'hot': 0, 'errors': 0}
        hot_sample = []
        dfh = open(done_p, 'a', encoding='utf-8')
        jl = open(os.path.join(_dirz, 'zakupki_stream.jsonl'), 'a', encoding='utf-8')
        for rev, inn, name in chunk:
            z = find_zakupki_contacts(inn, max_cards=int(args.get('max_cards', 3)))
            st['processed'] += 1
            jl.write(json.dumps({'inn': inn, 'name': name, 'rev': rev, 'z': z},
                                ensure_ascii=False) + '\n')
            jl.flush()
            dfh.write(inn + '\n')
            dfh.flush()
            if not z or z.get('error'):
                st['errors'] += 1 if (z or {}).get('error') else 0
                continue
            got = hot = False
            for c in (z.get('cards') or []):
                if c.get('email') and db is not None:
                    got = True
                    try:
                        db.add_email(inn, c['email'], role='закупки (конт. лицо)',
                                     person=c.get('contact_person') or '',
                                     source='zakupki:eis', source_url=c.get('url') or '')
                    except Exception:  # noqa: BLE001
                        pass
                if ZK_HOT.search(c.get('title') or ''):
                    hot = True
                    if len(hot_sample) < 6:
                        hot_sample.append({'inn': inn, 'name': name, 'title': c.get('title')})
                    if db is not None:
                        try:
                            db.add_signal(inn, source='zakupki:eis', event_type='закупка-оборудование',
                                          what=(c.get('title') or '')[:140], hotness=4,
                                          source_url=c.get('url') or '', ts='')
                        except Exception:  # noqa: BLE001
                            pass
            st['with_contacts'] += 1 if got else 0
            st['hot'] += 1 if hot else 0
        dfh.close()
        jl.close()
        # самочейн со своим стоп-флагом
        chained = ''
        if args.get('chain') and len(rows) > cap:
            drop = os.environ.get('DROP_URL', '').rstrip('/')
            tokd = os.environ.get('DROP_TOKEN', '')
            sec = os.environ.get('JOB_HMAC', '')
            import hmac as _h
            import hashlib as _hl
            try:
                req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tokd})
                names = [f.get('name') for f in json.loads(urllib.request.urlopen(req, timeout=30).read())]
                if 'zakupki_stop.flag' in names:
                    chained = 'stopped-by-flag'
                else:
                    jid = f'{int(time.time())}-zkmass{os.getpid()}'
                    job = {'id': jid, 'task': 'enrich_contacts', 'args': args, 'ts': int(time.time())}
                    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False)
                    if sec:
                        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
                    rq = urllib.request.Request(drop + f'/job-{jid}.json',
                                                data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                                                method='PUT', headers={'X-Drop-Token': tokd})
                    urllib.request.urlopen(rq, timeout=60)
                    chained = jid
            except Exception as e:  # noqa: BLE001
                chained = f'chain-err:{str(e)[:60]}'
        json.dump({'op': 'zakupki_mass', **st, 'left': len(rows) - len(chunk),
                   'hot_sample': hot_sample, 'chained': chained}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'zakupki_probe':
        # тест ЕИС-контактов: inns -> find_zakupki_contacts
        out = [find_zakupki_contacts(i, max_cards=int(args.get('max_cards', 3)))
               for i in (args.get('inns') or [])[:5]]
        json.dump({'op': 'zakupki_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'vk_probe':
        out = []
        _vtok = _read_secret('VK_TOKEN_USER') or _read_secret('VK_TOKEN')
        for n in (args.get('names') or [])[:10]:
            row = dict(name=n, vk=find_vk_group_contacts({'name': n}))
            if args.get('debug'):
                try:
                    _nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|КАО|ГК)\s+', '', n).strip('"«» ')
                    _u = ('https://api.vk.com/method/groups.search?q=' + urllib.parse.quote(_nm)
                          + '&count=5&type=group&access_token=' + _vtok + '&v=5.199')
                    _r = _DIRECT.open(urllib.request.Request(_u, headers={'User-Agent': VC.UA}), timeout=20)
                    _d = json.loads(_r.read())
                    if 'error' in _d:
                        row['raw_err'] = _d['error'].get('error_msg', '')[:120]
                    else:
                        row['raw_groups'] = [{'name': g.get('name'), 'screen': g.get('screen_name')}
                                             for g in (_d.get('response', {}).get('items') or [])[:5]]
                except Exception as e:  # noqa: BLE001
                    row['raw_err'] = f'{type(e).__name__}: {str(e)[:100]}'
            out.append(row)
        json.dump({'op': 'vk_probe', 'token_present': bool(_vtok), 'results': out},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hh_probe':
        # адресная hh-проверка (тест). debug=true -> сырые кандидаты-работодатели
        out = []
        for n in (args.get('names') or [])[:15]:
            row = dict(name=n, hh=find_hh_compressor({'name': n}))
            if args.get('debug'):
                try:
                    _q = urllib.parse.quote(re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО)\s+', '', n).strip('"«» '))
                    _url = 'https://api.hh.ru/employers?text=' + _q + '&only_with_vacancies=true&per_page=5'
                    # 1) прямой
                    try:
                        _rq = urllib.request.Request(_url, headers={'User-Agent': 'RuspromLeadEnrich/1.0 (kirillrand4@gmail.com)', 'Accept': 'application/json'})
                        _jd = json.loads(_DIRECT.open(_rq, timeout=15).read())
                        row['direct'] = 'ok'; row['raw_employers'] = [e.get('name') for e in (_jd.get('items') or [])]
                    except Exception as _de:  # noqa: BLE001
                        row['direct'] = f'{type(_de).__name__}: {str(_de)[:50]}'
                        # 2) дельфин
                        import browser_probe as BP
                        _dtok2 = _read_secret('DOLPHIN_TOKEN')
                        _dprofs2 = _resolve_dolphin_profiles(None, _dtok2)
                        _dpid = _dprofs2[0] if _dprofs2 else None
                        _out = BP.probe({'url': _url, 'return_html': True, 'html_cap': 100000,
                                         'wait_ms': 3500, 'screenshot': False, 'solve': True,
                                         'dolphin_profile': _dpid, 'dolphin_token': _dtok2})
                        _body = (_out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', _out.get('html') or '')
                        row['dolphin_len'] = len(_body); row['dolphin_head'] = _body[:200]
                        row['dolphin_captcha'] = _out.get('captcha_type')
                        _m = re.search(r'\{.*\}', _body, re.S)
                        if _m:
                            try:
                                row['dolphin_employers'] = [e.get('name') for e in (json.loads(_m.group(0)).get('items') or [])]
                            except Exception as _je:  # noqa: BLE001
                                row['dolphin_parse_err'] = str(_je)[:60]
                except Exception as e:  # noqa: BLE001
                    row['raw_err'] = f'{type(e).__name__}: {str(e)[:120]}'
            out.append(row)
        json.dump({'op': 'hh_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'resolve_test':
        # РУЧНОЙ резолв имён -> ИНН той же цепочкой, что ingest_noinn (диагностика/точечное
        # использование). args: {names:[...], no_serp:bool}
        import news_scan as NS
        _tok = _read_secret('DADATA_TOKEN')
        # сырой пробник dadata с сервера: код/тело ошибки (news_scan глотает исключения)
        raw_probe = {}
        try:
            _b = json.dumps({'query': 'Фармасинтез', 'count': 1}).encode()
            _rq = urllib.request.Request(
                'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                data=_b, method='POST', headers={'Content-Type': 'application/json',
                'Accept': 'application/json', 'Authorization': f'Token {_tok}'})
            _resp = urllib.request.urlopen(_rq, timeout=25)
            raw_probe = {'http': _resp.status,
                         'n_sugg': len(json.loads(_resp.read()).get('suggestions') or [])}
        except urllib.error.HTTPError as e:
            raw_probe = {'http': e.code, 'body': e.read()[:200].decode('utf-8', 'replace')}
        except Exception as e:  # noqa: BLE001
            raw_probe = {'error': f'{type(e).__name__}: {str(e)[:150]}'}
        out = []
        for name in (args.get('names') or [])[:30]:
            row = {'name': name, 'token_seen': bool(_tok)}
            try:
                row['variants'] = NS._name_variants(name)
                dd = NS.dadata_suggest(name, _tok)
                if dd:
                    row.update(via='dadata', inn=dd.get('inn'), resolved=dd.get('name'),
                               conf=dd.get('confidence'))
                out.append(row)
            except Exception as e:  # noqa: BLE001
                row['error'] = f'{type(e).__name__}: {str(e)[:120]}'
                out.append(row)
        json.dump({'op': 'resolve_test', 'dadata_raw_probe': raw_probe, 'results': out},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'ingest_noinn':
        # ИНГЕСТЕР лидов БЕЗ ИНН из news_stream.jsonl (владелец: «самый большой источник
        # потерь», идея SERP-резолва — его). Цепочка: (1) dadata-варианты с расклонкой
        # (news_scan.dadata_suggest, дешёво) -> (2) SERP «"имя" ИНН» через xmlriver, регекс
        # ИНН из сниппетов справочников + чексумма + обратная верификация dadata findById
        # (матч имени — чужой ИНН не приклеим). Резолвнутые уходят в enrich.db (companies +
        # signals) = попадают в скоринг и лид-деск. Прогресс durable (.resolved-файл).
        import news_scan as NS
        ddtok = _read_secret('DADATA_TOKEN')
        _dirn = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(_dirn, args.get('stream', 'news_stream.jsonl'))
        done_path = path + '.resolved'

        def _inn_valid(inn):
            s = str(inn)
            if not s.isdigit() or len(s) not in (10, 12):
                return False
            def ctl(digs, w):
                return str(sum(int(d) * k for d, k in zip(digs, w)) % 11 % 10)
            if len(s) == 10:
                return s[9] == ctl(s, (2, 4, 10, 3, 5, 9, 4, 6, 8))
            return (s[10] == ctl(s, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
                    and s[11] == ctl(s, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)))

        def _serp_inn(name):
            """xmlriver Яндекс «"имя" ИНН» -> кандидаты ИНН из сниппетов (по порядку выдачи)."""
            user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
            if not (user and key):
                return []
            q = f'"{name}" ИНН'
            url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
                   + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
                   + '&query=' + urllib.parse.quote(q))
            xml = None
            for att in range(3):
                try:
                    with _SEM_XMLRIVER:
                        xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
                    if 'свободных каналов' in xml:
                        xml = None; time.sleep(1.5 * (att + 1)); continue
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(1.5 * (att + 1))
            if not xml:
                return []
            _bump('xmlriver')
            out, seen = [], set()
            for m in re.finditer(r'ИНН\D{0,10}(\d{12}|\d{10})', xml):
                inn = m.group(1)
                if inn not in seen and _inn_valid(inn):
                    seen.add(inn); out.append(inn)
            return out

        def _dd_findbyid(inn):
            try:
                body = json.dumps({'query': str(inn)}).encode()
                req = urllib.request.Request(
                    'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                    data=body, method='POST', headers={'Content-Type': 'application/json',
                    'Accept': 'application/json', 'Authorization': f'Token {ddtok}'})
                d = json.loads(urllib.request.urlopen(req, timeout=25).read())
                s = (d.get('suggestions') or [])
                if not s:
                    return None
                dd = s[0].get('data', {})
                return {'inn': dd.get('inn'), 'name': s[0].get('value'),
                        'okved': dd.get('okved') or '',
                        'region': ((dd.get('address') or {}).get('data') or {}).get('region'),
                        'status': (dd.get('state') or {}).get('status')}
            except Exception:  # noqa: BLE001
                return None

        done = {}
        try:
            for line in open(done_path, encoding='utf-8'):
                try:
                    j = json.loads(line); done[j['k']] = j
                except Exception:  # noqa: BLE001
                    continue
        except FileNotFoundError:
            pass
        recs = []
        try:
            for line in open(path, encoding='utf-8'):
                try:
                    r = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if not r.get('inn') and r.get('company'):
                    recs.append(r)
        except FileNotFoundError:
            json.dump({'op': 'ingest_noinn', 'error': f'нет {path}'}, sys.stdout, ensure_ascii=False)
            return
        byname = {}
        for r in recs:  # дедуп по нормализованному имени (последняя запись побеждает)
            k = re.sub(r'[^а-яёa-z0-9 ]', '', r['company'].lower()).strip()[:60]
            if k:
                byname[k] = r
        retry_un = bool(args.get('retry_unresolved', False))
        items = [(k, v) for k, v in byname.items()
                 if k not in done or (retry_un and not done[k].get('inn'))]
        cap = int(args.get('cap', 0))
        if cap:
            items = items[:cap]
        db = None
        if args.get('write_db', True):
            try:
                import enrich_db as EDB
                db = EDB.EnrichDB()
            except Exception:  # noqa: BLE001
                pass
        dfh = open(done_path, 'a', encoding='utf-8')
        resolved = 0; via_cnt = {}; samples = []; unresolved_sample = []
        _ing_lock = threading.Lock()

        def _ing_one(kv):
            nonlocal resolved
            k, r = kv
            name = r['company']
            dd = NS.dadata_suggest(name, ddtok)
            via = 'dadata' if dd else None
            if not dd and not args.get('no_serp'):
                for inn in _serp_inn(name)[:3]:
                    fb = _dd_findbyid(inn)
                    if fb and NS._match_score(name, fb['name']) >= 1:
                        dd = {**fb, 'confidence': 'serp'}
                        via = 'serp'; break
            with _ing_lock:  # БД + done-файл + счётчики под одним локом (sqlite одно соединение)
                if dd and dd.get('inn'):
                    resolved += 1
                    via_cnt[via] = via_cnt.get(via, 0) + 1
                    if db is not None:
                        try:
                            db.upsert_company(dd['inn'], name=dd.get('name') or name,
                                              division=NS.division_of(dd.get('okved') or ''),
                                              okved=dd.get('okved') or '',
                                              region=dd.get('region') or r.get('region') or '')
                            db.add_signal(dd['inn'],
                                          source=r.get('source_name') or r.get('collector') or 'news',
                                          event_type=r.get('event_type') or '', what=r.get('what') or '',
                                          sum=str(r.get('sum') or ''), source_url=r.get('source_url') or '',
                                          hotness=int(r.get('hotness') or 0), ts=r.get('published') or '')
                            for _em in _egrul_emails_by_inn(dd['inn']):
                                db.add_email(dd['inn'], _em, role='юрзначимый (ЕГРЮЛ)',
                                             source='egrul:dadata', source_url='')
                        except Exception:  # noqa: BLE001
                            pass
                    if len(samples) < 8:
                        samples.append({'company': name, 'resolved': dd.get('name'),
                                        'inn': dd['inn'], 'via': via,
                                        'conf': dd.get('confidence', '')})
                    dfh.write(json.dumps({'k': k, 'inn': dd['inn'], 'via': via},
                                         ensure_ascii=False) + '\n')
                else:
                    if len(unresolved_sample) < 10:
                        unresolved_sample.append(name[:60])
                    dfh.write(json.dumps({'k': k, 'inn': None}, ensure_ascii=False) + '\n')
                dfh.flush()

        # ПАРАЛЛЕЛЬНО (последовательно 150 имён не влезали в таймаут джобы 1800с):
        # dadata тред-безопасен, xmlriver под _SEM_XMLRIVER — каналы не переливаются.
        _iw = max(1, min(int(args.get('workers', 10)), 20))
        with ThreadPoolExecutor(max_workers=_iw) as _ex:
            list(_ex.map(_ing_one, items))
        dfh.close()
        # сводка по ВСЕМУ .resolved-файлу (включая прошлые прогоны — отчёт таймаутнутого
        # прогона теряется, а done-файл durable и хранит всю правду)
        d_tot = d_inn = 0; d_via = {}
        try:
            for line in open(done_path, encoding='utf-8'):
                try:
                    j = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                d_tot += 1
                if j.get('inn'):
                    d_inn += 1
                    d_via[j.get('via') or '?'] = d_via.get(j.get('via') or '?', 0) + 1
        except FileNotFoundError:
            pass
        json.dump({'op': 'ingest_noinn', 'stream_noinn_records': len(recs),
                   'unique_names': len(byname), 'already_done': len(byname) - len(items),
                   'processed': len(items), 'resolved': resolved, 'via': via_cnt,
                   'resolve_rate': round(resolved / len(items), 3) if items else None,
                   'samples': samples, 'unresolved_sample': unresolved_sample,
                   'done_total': {'names': d_tot, 'with_inn': d_inn, 'via': d_via,
                                  'rate': round(d_inn / d_tot, 3) if d_tot else None}},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'envcheck':
        # диагностика ключей: (a) видит ли раннер в окружении, (b) есть ли в файле
        # runner-secrets.env (владелец мог добавить, но не рестартнуть раннер). Значений НЕ показываем.
        import os as _os
        keys = ['CAPMONSTER_KEY', 'TWOCAPTCHA_KEY', 'RUCAPTCHA_KEY', 'DOLPHIN_TOKEN',
                'XMLRIVER_USER', 'XMLRIVER_KEY', 'PROVIDER_API_KEY', 'VK_TOKEN']
        in_env = {k: bool(_os.environ.get(k)) for k in keys}
        # проверяем ОБА runner-secrets.env (локальный + стабильный на дропе)
        def _parse(fp):
            out = {}
            try:
                if _os.path.exists(fp):
                    for line in open(fp, encoding='utf-8-sig'):
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        kk, vv = line.split('=', 1)
                        out[kk.strip()] = vv.strip()
            except Exception:  # noqa: BLE001
                pass
            return out
        files = {}
        for fp in _SECRET_FILES:
            parsed = _parse(fp)
            files[fp] = {'exists': _os.path.exists(fp),
                         'keys': {k: bool(parsed.get(k) and not parsed.get(k, '').startswith('<'))
                                  for k in keys}}
        # эффективно доступно (env ИЛИ любой файл) — как реально увидит код
        effective = {k: bool(_read_secret(k)) for k in keys}
        json.dump({'op': 'envcheck', 'in_runner_env': in_env, 'files': files,
                   'effective_available': effective,
                   'note': 'effective_available=true -> код увидит ключ (даже если раннер env не подхватил)'},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'smtp_selftest':
        # self-тест реальной отправки через движок панели (ящики s1/s2). Пишет письмо
        # ОДНОГО ящика ДРУГОМУ через Sender.send_reply(live=True) — тот же путь, что
        # ручная отправка в вебе. Гоняется из песочницы через runner (env сервера).
        out = {'op': 'smtp_selftest'}
        try:
            sys.path.insert(0, r'C:\sender')
            import os as _os
            _os.chdir(r'C:\sender')
            # пароли ящиков можно передать прямо в джобе (args.pw = {env_name: пароль}) —
            # подставляем в окружение процесса ДО валидации конфига. Так тест-цикл
            # закрывается без правки env службы. Тестовые ящики; джоб чистим с дропа.
            for _k, _v in (args.get('pw') or {}).items():
                if _k and _v:
                    _os.environ[str(_k)] = str(_v)
            from sender.config import Config as _Cfg
            from sender.store import Store as _St
            from sender.wiring import build_deps as _bd
            cfg = _Cfg.load(_os.getenv('SENDER_CONFIG', './sender.yaml'), env=_os.environ)
            st = _St(cfg.get('service.db_path', 'sender.db')); st.init_schema()
            try:
                cfg.load_mailbox_overrides(st)
            except Exception:  # noqa: BLE001
                pass
            mbs = cfg.mailboxes()
            out['mailboxes'] = [{'id': m.mailbox_id, 'smtp': f'{m.smtp_host}:{m.smtp_port}',
                                 'login': m.login, 'env': m.password_env,
                                 'pw_set': bool(_os.environ.get(m.password_env))} for m in mbs]
            frm = args.get('from') or next((m.mailbox_id for m in mbs
                                            if m.mailbox_id.startswith('s1@')), None)
            to = args.get('to') or next((m.mailbox_id for m in mbs
                                         if m.mailbox_id.startswith('s2@')), None)
            if frm and to:
                deps = _bd(cfg, st)
                res = deps.sender.send_reply(mailbox_id=frm, to_email=to,
                    subject=args.get('subject', 'selftest'),
                    body=args.get('body', 'Проверка реальной отправки. ООО «Руспром»'), live=True)
                out.update({'sent': True, 'from': frm, 'to': to,
                            'dry_run': res.dry_run, 'msgid': res.rfc_message_id})
            else:
                out['sent'] = False; out['error'] = 'нет s1/s2 среди ящиков'
        except Exception as e:  # noqa: BLE001
            out['sent'] = False; out['error'] = repr(e)[:400]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('read_stream'):
        # вернуть записи из jsonl на сервере (для оффлайн модель-сравнения на крауленных текстах)
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          os.path.basename(str(args['read_stream'])))
        recs, lim = [], int(args.get('limit', 200))
        try:
            with open(fp, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        recs.append(json.loads(line))
                    except Exception:  # noqa: BLE001
                        continue
                    if len(recs) >= lim:
                        break
        except Exception as e:  # noqa: BLE001
            json.dump({'error': f'read-fail:{str(e)[:80]}', 'path': fp}, sys.stdout, ensure_ascii=False)
            return
        json.dump({'records': recs, 'count': len(recs)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('base_cities'):
        # ВСЕ уникальные населённые пункты из юрадресов базы [9] (формат ЕГРЮЛ:
        # «443058, Самарская область, г. о. Самара, г. Самара, ул. Физкультурная, ...»).
        # Токенизируем по запятым; маркеры типов НП; «г. о.» (гор. округ), «с. п.» (сельское
        # поселение), «м. о.» (мун. округ) — НЕ населённые пункты, исключаем. Берём ПОСЛЕДНИЙ
        # маркер-совпадение (самый специфичный: город идёт до улицы, деревня — после района).
        import csv
        p = _get_base()
        if not p:
            json.dump({'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        ADDR, REG = 9, 10
        try:
            csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        MARKERS = [  # (тип, regex по токену)
            ('г', re.compile(r'^(?:г\.|город)\s*(?!о\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('пгт', re.compile(r'^(?:пгт\.?|п\.\s*г\.\s*т\.?)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('рп', re.compile(r'^рп\.?\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('с', re.compile(r'^(?:с\.|село)\s*(?!п\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('п', re.compile(r'^(?:п\.|пос\.|посёлок|поселок)\s*(?!г\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('д', re.compile(r'^(?:д\.|дер\.|деревня)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('х', re.compile(r'^(?:х\.|хутор)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('ст-ца', re.compile(r'^(?:ст-ца|станица)\s+([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('аул', re.compile(r'^аул\s+([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
        ]
        seen = {}
        scanned = parsed = 0
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
                scanned += 1
                if len(row) <= REG:
                    continue
                addr = (row[ADDR] or '')
                reg = (row[REG] or '').strip()
                hit = None
                for tok in (t.strip() for t in addr.split(',')):
                    tok = re.sub(r'\s+', ' ', tok)
                    for typ, rx in MARKERS:
                        m = rx.match(tok)
                        if m:
                            hit = (typ, m.group(1).strip())
                for_typ_city = hit
                if for_typ_city:
                    parsed += 1
                    typ, city = for_typ_city
                    k = (city, reg)
                    if k in seen:
                        seen[k]['n'] += 1
                    else:
                        seen[k] = {'city': city, 'type': typ, 'region': reg, 'n': 1}
        out = sorted(seen.values(), key=lambda x: -x['n'])
        json.dump({'scanned': scanned, 'with_settlement': parsed, 'unique': len(out),
                   'settlements': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('base_peek'):
        json.dump(_base_peek(int(args.get('n', 3))), sys.stdout, ensure_ascii=False)
        return
    if args.get('base_pick'):
        json.dump(_base_pick(no_site=args.get('no_site', True),
                             size_col=args.get('size_col'), limit=int(args.get('limit', 500)),
                             okved_prefixes=set(args['okved_prefixes']) if args.get('okved_prefixes') else None),
                  sys.stdout, ensure_ascii=False)
        return
    companies = args.get('companies', [])
    # РЕЗЮМИРУЕМОСТЬ списка компаний (автономная ночь: раннер перезапускается на бэр-python,
    # длинный джоб иначе переобрабатывается с нуля). resume=true -> пропускаем ИНН, уже
    # сделанные в stream_file (по _done_inns). Так рестарт продолжает, а не дублирует.
    if companies and args.get('resume'):
        try:
            import glob as _rg
            _sf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               args.get('stream_file', 'enrich_stream.jsonl'))
            _done = set()
            for _fp in _rg.glob(_sf) + _rg.glob(_sf.rsplit('.', 1)[0] + '*.jsonl'):
                try:
                    for _ln in open(_fp, encoding='utf-8'):
                        try:
                            _j = json.loads(_ln)
                            _inn = str(_j.get('inn') or '')
                            # сделано = есть email ИЛИ verified ИЛИ явный «нет контактов» без ошибки-транзиента
                            if _inn and (_j.get('emails') or _j.get('best_for_outreach')
                                         or _j.get('verified') or _j.get('method') == 'ok'):
                                _done.add(_inn)
                        except Exception:  # noqa: BLE001
                            continue
                except Exception:  # noqa: BLE001
                    continue
            _before = len(companies)
            companies = [c for c in companies if str(c.get('inn') or '') not in _done]
            sys.stderr.write(f'resume: было {_before}, к обработке {len(companies)} (done {len(_done)})\n')
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
    # МАССОВЫЙ прогон по базе (финальная задача: xmlriver-поиск сайта + выгрузка контактов
    # для ВСЕЙ базы без сайта). Резюмируемо: пропускаем уже сделанные ИНН (из jsonl). Берём
    # по убыванию выручки (лучшие лиды первыми). cap>0 — ограничить пачку (валидация/бюджет).
    if args.get('mass_base'):
        _dirm = os.path.dirname(os.path.abspath(__file__))
        done = _done_inns(_dirm)
        allc = _base_pick(no_site=args.get('no_site', True), size_col=args.get('size_col'),
                          limit=10 ** 9,
                          okved_prefixes=set(args['okved_prefixes']) if args.get('okved_prefixes') else None)
        pool = allc.get('companies', []) if isinstance(allc, dict) else []
        todo = [c for c in pool if str(c.get('inn') or '') not in done]
        cap = int(args.get('cap', 0))
        if cap > 0:
            todo = todo[:cap]
        companies = todo
        # САМОЧЕЙНИНГ: если есть работа и chain=True — сразу пишем следующий job на дроп (в
        # начале, чтобы пережить таймаут раннера). Раннер серийный → преемник запустится после
        # этого чанка, его done-set уже включит наши ИНН. Пустой пул → чейна нет → стоп.
        if args.get('chain') and companies:
            ch = _chain_next(args)
            sys.stderr.write(f'chain-next: {ch}\n')
        sys.stderr.write(f'mass_base: no-site всего={len(pool)}, done={len(done)}, '
                         f'к обработке={len(companies)} (cap={cap or "нет"})\n')
        sys.stderr.flush()
    # НОВОСТНЫЕ КОМПАНИИ: контакты для компаний с новостным сигналом. Владелец: новостные лиды
    # ценные → обогащаем ПОЛНОСТЬЮ (xmlriver + все фолбэки + браузер, «всё что можно»), не
    # ограничиваясь известным сайтом [20]; базовый сайт — лишь последний фолбэк (base_site). ГЕЙТ
    # уточнён: пропускаем только тех, у кого уже есть ПОДТВЕРЖДЁННЫЙ контакт; «сходили-пусто» по
    # горячему сигналу перепробуем (кап попыток). Резюмируемо + чейнинг. По умолчанию ВЫКЛ.
    if args.get('news_enrich'):
        import glob as _glob
        _dirm = os.path.dirname(os.path.abspath(__file__))
        _NEWS_RETRY = int(args.get('news_retry', 2))   # перепробовать «пустые» не более N раз
        verified, all_inns = set(), []
        try:
            import enrich_db as EDB
            _cx = EDB.EnrichDB().cx
            all_inns = [r[0] for r in _cx.execute(
                "SELECT DISTINCT inn FROM signals WHERE inn!='' AND inn IS NOT NULL").fetchall()]
            # «обогащён» = есть ПОДТВЕРЖДЁННЫЙ контакт (verified ∈ {inn,ogrn,phone,provider} + email)
            verified = {r[0] for r in _cx.execute(
                "SELECT DISTINCT c.inn FROM companies c JOIN emails e ON e.inn=c.inn "
                "WHERE c.verified IN ('inn','ogrn','phone','provider')").fetchall()}
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'news_enrich: db err {str(e)[:80]}\n')
        # счётчик попыток по ИНН из новостного потока — «пустые» перепроверяем, но с капом
        # (иначе цепочка зациклится на компаниях без email). Поток тот же, что пишет main().
        _pref = args.get('stream_file', 'enrich_stream.jsonl').rsplit('.', 1)[0]
        attempts = {}
        for fp in _glob.glob(os.path.join(_dirm, _pref + '*.jsonl')):
            try:
                with open(fp, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            _inn = str(json.loads(line).get('inn') or '')
                        except Exception:  # noqa: BLE001
                            continue
                        if _inn:
                            attempts[_inn] = attempts.get(_inn, 0) + 1
            except Exception:  # noqa: BLE001
                pass
        exhausted = {i for i, c in attempts.items() if c >= _NEWS_RETRY}
        skip = verified | exhausted
        todo_inns = [i for i in all_inns if str(i) not in skip]
        idx = _base_index(set(str(i) for i in todo_inns))
        # обогащаем полностью через xmlriver: сайт из базы [20] НЕ ставим в site (иначе краул
        # пойдёт по нему без xmlriver), а кладём в base_site как последний фолбэк. city/phones —
        # для xmlriver-запроса и верификации сайта.
        # имя/регион из enrich.db — фолбэк для новостных компаний ВНЕ базы обзвона
        # (например, спасённые ингестером): без имени xmlriver-запрос сломан
        db_names = {}
        try:
            for r_ in _cx.execute('SELECT inn,name,region FROM companies').fetchall():
                db_names[str(r_[0])] = (r_[1] or '', r_[2] or '')
        except Exception:  # noqa: BLE001
            pass
        companies = []
        for i in todo_inns:
            bi = idx.get(str(i), {})
            nm = bi.get('name', '') or db_names.get(str(i), ('', ''))[0]
            ct = bi.get('city', '') or db_names.get(str(i), ('', ''))[1]
            companies.append(dict(inn=str(i), name=nm, city=ct,
                                  phones=bi.get('phones', []), base_site=bi.get('site', '')))
        companies = [c for c in companies if c['name']]   # без имени обогащать нечем
        cap = int(args.get('cap', 0))
        if cap > 0:
            companies = companies[:cap]
        if args.get('chain') and companies:
            sys.stderr.write(f'chain-next: {_chain_next(args)}\n')
        sys.stderr.write(f'news_enrich: сигналов-ИНН={len(all_inns)}, verified-skip={len(verified)}, '
                         f'retry-исчерпано={len(exhausted)}, к обработке={len(companies)}\n')
        sys.stderr.flush()
    # диагностика карточки Яндекса: сырой блок knowledge_graph для проверки полей (есть ли
    # email/сайт/телефон). Не тратит provider/браузер — только xmlriver по компании.
    if args.get('kg_probe'):
        out = []
        for c in companies[:8]:
            site, src, card = find_site_via_xmlriver(c)
            row = {'name': c.get('name'), 'site': site, 'src': src, 'card': card}
            try:
                user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
                nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', c.get('name', '')).strip().strip('"«»')
                q = f'{nm} {c.get("city", "")} официальный сайт'.strip()
                u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
                     + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
                     + '&additional=knowledge_graph_y&query=' + urllib.parse.quote(q))
                xml = _DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
                mm = re.search(r'<knowledge_graph\b.*?</knowledge_graph>', xml, re.S)
                row['raw_kg'] = mm.group(0)[:2000] if mm else None
            except Exception as e:  # noqa: BLE001
                row['raw_err'] = str(e)[:60]
            out.append(row)
        json.dump({'kg_probe': out, 'cost': dict(_COST)}, sys.stdout, ensure_ascii=False)
        return
    pace = (float(args.get('pace_min', 6.0)), float(args.get('pace_max', 14.0)))
    workers = max(1, min(int(args.get('workers', 6)), 80))  # прямой HTTP лёгкий → потолок выше
    # управление параллелизмом (сервер мощный → можно поднять)
    global _NO_BROWSER, _SEM_BROWSER, _USE_FALLBACK, _RETURN_TEXT, _SKIP_PROVIDER
    global _DOLPHIN_TOKEN, _DOLPHIN_PROFILES, _SEM_XMLRIVER
    # число каналов xmlriver управляемо из args (env XMLRIVER_CHANNELS не долетает до сервера)
    if args.get('channels'):
        _SEM_XMLRIVER = threading.Semaphore(max(1, int(args['channels'])))
    # МОДЕЛЬ extract_roles: массовый вал → haiku (9× дешевле, ~90%, проверено); иначе fable.
    VC._PROVIDER_MODEL = args.get('extract_model') or (
        'claude-haiku-4-5' if (args.get('mass_base') or args.get('news_enrich')) else 'claude-fable-5')
    # таймаут краул-fetch: мёртвые сайты не держат воркер по 45-90с (массовый прогон)
    if args.get('fetch_timeout'):
        VC._FETCH_TIMEOUT = int(args['fetch_timeout'])
    _NO_BROWSER = bool(args.get('no_browser', False))
    _USE_FALLBACK = not bool(args.get('no_fallback', False))
    _RETURN_TEXT = bool(args.get('return_text', False))
    _SKIP_PROVIDER = bool(args.get('skip_provider', False))
    globals()['_NO_STAFF_SEARCH'] = bool(args.get('no_staff_search', False))
    globals()['_NO_DIR_LOOKUP'] = bool(args.get('no_dir_lookup', False))
    globals()['_OPO_CHECK'] = bool(args.get('opo_check', False))
    globals()['_DISCOVERY_ONLY'] = bool(args.get('discovery_only', False))
    globals()['_HH_CHECK'] = bool(args.get('hh_check', False))
    globals()['_NO_SITE_CACHE'] = bool(args.get('no_site_cache', False))
    globals()['_NO_VK_LOOKUP'] = bool(args.get('no_vk_lookup', False))
    globals()['_ZAKUPKI_CHECK'] = bool(args.get('zakupki_check', False))
    globals()['_SMTP_CHECK'] = bool(args.get('smtp_check', False))
    if args.get('site_cache_days'):
        globals()['_SITE_CACHE_DAYS'] = int(args['site_cache_days'])
    # токен — из args ИЛИ env ИЛИ любого runner-secrets.env (устойчиво к удалению локального
    # файла: есть стабильная копия на дропе). Профили пока только из args.
    _DOLPHIN_TOKEN = args.get('dolphin_token', '') or _read_secret('DOLPHIN_TOKEN')
    _DOLPHIN_PROFILES = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _DOLPHIN_TOKEN)
    bw = max(1, min(int(args.get('browser_workers', 2)), 30))
    _SEM_BROWSER = threading.Semaphore(bw)

    # ИНКРЕМЕНТАЛЬНАЯ запись в ДВА места разными способами (переживает таймаут/рестарт;
    # если один файл побьётся — второй цел): (1) enrich.db SQLite/WAL, (2) enrich_stream.jsonl
    # append-only (битая строка не рушит остальные; из него восстановима БД). Пишем СРАЗУ
    # по готовности компании, а не в конце.
    _wr = bool(args.get('write_db', True))
    _db = None
    _jsonl = None
    _wlock = threading.Lock()
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _wr:
        try:
            import enrich_db as EDB
            _db = EDB.EnrichDB()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'enrich_db init skip: {str(e)[:100]}\n')
        try:
            _jsonl = open(os.path.join(_dir, args.get('stream_file', 'enrich_stream.jsonl')),
                          'a', encoding='utf-8')
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'jsonl init skip: {str(e)[:100]}\n')
    cin = {str(c.get('inn')): c for c in companies if c.get('inn')}

    def _persist(r):
        inn = str(r.get('inn') or '')
        if not inn or not _wr:
            return
        src = cin.get(inn, {})
        with _wlock:
            # (1) JSONL — максимально устойчивый: append + flush + fsync
            if _jsonl is not None:
                try:
                    rec = dict(r)
                    rec['_okved'] = src.get('okved')
                    rec['_src'] = args.get('source') or 'enrich'
                    _jsonl.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    _jsonl.flush()
                    try:
                        os.fsync(_jsonl.fileno())
                    except Exception:  # noqa: BLE001
                        pass
                except Exception:  # noqa: BLE001
                    pass
            # (2) SQLite — структурированное, идемпотентно по ИНН
            if _db is not None:
                try:
                    # направление по ТОЧНОМУ маппингу владельца (основной [16] + ВСЕ доп [17])
                    div = src.get('division') or args.get('division')
                    if not div:
                        try:
                            import enrich_db as _E
                            div, _bud = _E.division_for_okveds(src.get('okved'), src.get('okved_all'))
                        except Exception:  # noqa: BLE001
                            div = None
                    # сайт: подтверждённый → site; неподтверждённый → cand_site (в базе для
                    # ручной сверки, но не как настоящий); mismatch → не пишем. И НЕ ТРОГАЕМ, если
                    # у компании уже есть положительный verified (не затираем подтверждённое).
                    _ver = r.get('verified'); _sv = r.get('site')
                    _conf = _ver in ('inn', 'ogrn', 'phone', 'provider')
                    _ex = _db.cx.execute('SELECT verified FROM companies WHERE inn=?', (inn,)).fetchone()
                    _already = bool(_ex and _ex[0] in ('inn', 'ogrn', 'phone', 'provider'))
                    if _already:
                        ver_w = site_w = cand_w = None          # уже подтверждён — не трогаем
                    elif _conf:
                        ver_w, site_w, cand_w = _ver, _sv, None
                    elif _ver == 'mismatch':
                        ver_w, site_w, cand_w = _ver, None, None  # метку пишем, чужой сайт — нет
                    else:
                        ver_w, site_w, cand_w = _ver, None, _sv   # кандидат на ручную сверку
                    _db.upsert_company(
                        inn, name=r.get('name') or src.get('name'),
                        division=div or None,
                        okved=src.get('okved'), region=src.get('city') or src.get('region'),
                        pxr=src.get('pxr'), site=site_w, cand_site=cand_w, activity=r.get('activity'),
                        is_competitor=r.get('is_competitor'), verified=ver_w,
                        best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                    for e in (r.get('emails') or []):
                        _db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                      person=e.get('person', ''), mx_ok=e.get('mx_ok'),
                                      source=args.get('source') or 'enrich',
                                      source_url=e.get('source_url') or '')
                except Exception:  # noqa: BLE001
                    pass

    def _one(c):
        try:
            r = enrich_one(c, pace)
        except Exception as e:  # noqa: BLE001
            r = {'inn': c.get('inn'), 'name': c.get('name'), 'error': f'exc:{str(e)[:80]}'}
        _persist(r)   # пишем СРАЗУ, не дожидаясь конца прогона
        return r

    # Параллельно МЕЖДУ компаниями (у каждой свой сайт). Discovery по общим хостам
    # (list-org/поисковик) сериализован семафором внутри enrich_one — один сайт не грузим.
    if workers > 1 and len(companies) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_one, companies))
    else:
        results = [_one(c) for c in companies]
    if _jsonl is not None:
        try:
            _jsonl.close()
        except Exception:  # noqa: BLE001
            pass
    from collections import Counter
    with_email = sum(1 for r in results if r.get('emails'))
    with_lpr = sum(1 for r in results if r.get('best_for_outreach'))
    site_src = Counter(r.get('site_source') for r in results if r.get('site_source'))
    json.dump({'results': results, 'count': len(results),
               'summary': {'with_email': with_email, 'with_lpr_email': with_lpr,
                           'site_sources': dict(site_src)},
               'cost': dict(_COST)},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
