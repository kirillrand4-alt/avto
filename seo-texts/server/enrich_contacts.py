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


def _next_dolphin_profile():
    if not _DOLPHIN_PROFILES:
        return None
    with _DOLPHIN_LOCK:
        i = _DOLPHIN_IDX[0] % len(_DOLPHIN_PROFILES)
        _DOLPHIN_IDX[0] += 1
    return _DOLPHIN_PROFILES[i]
_SKIP_PROVIDER = False  # не звать provider (только краул+regex) — быстрый сбор текстов


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
                 'office', 'сбыт', 'poставщик', 'postavshchik', 'kontakty')
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


def crawl_contacts(site, pace=(6.0, 14.0)):
    """Домашняя + страницы контактов -> объединённый текст (кап по объёму)."""
    pages, texts = [], []
    home, method, meta = _fetch_site(site)
    if not home or meta.get('captcha_type'):
        return '', [], f'site-block:{meta.get("captcha_type") or method}', {}
    texts.append(home)
    dom = _domain(site)
    links = re.findall(r'href="([^"]+)"', home)
    picked = []
    for l in links:
        ll = l.lower()
        if any(h in ll for h in CONTACT_HINTS):
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/"+l}'
            if _domain(full) == dom and full not in picked:
                picked.append(full)
        if len(picked) >= 6:
            break
    for u in picked:
        time.sleep(_PACE(*pace))
        h, m, mt = _fetch_site(u)
        if h and not mt.get('captcha_type'):
            texts.append(h)
            pages.append(u)
    # склеиваем текст, режем теги, кап
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
    for e in srcmap:
        pos = low.find(e)
        ctx = re.sub(r'\s+', ' ', txt[max(0, pos - 70):pos + len(e) + 20]).strip() if pos >= 0 else ''
        per[e] = {'src': srcmap[e], 'local': e.split('@')[0], 'ctx': ctx}
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


def enrich_one(company, pace):
    r = {'inn': company.get('inn'), 'name': company.get('name')}
    # пре-фильтр конкурентов (производители компрессоров) — не тратим на них разведку
    if _is_competitor(company):
        r.update({'method': 'competitor-skip', 'is_competitor': True,
                  'error': 'конкурент (производитель компрессоров/насосов)'})
        return r
    site = company.get('site')
    src = 'given'
    card = {}
    tmr = {}
    if not site or not _is_own_site(site if site.startswith('http') else 'http://' + site):
        # ОСНОВНОЙ канал — xmlriver (чистый SERP, без капчи/прокси); фолбэки — list-org и
        # DDG под семафором=1 (не грузить один хост). На массовом прогоне фолбэки ЖГУТ
        # время (сериализуют все воркеры + хардкод-паузы) — _USE_FALLBACK их выключает.
        _t0 = time.time()
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
        r['error'] = f'сайт не найден ({src})' + (' [карточка Я есть]' if card else '')
        r['method'] = src
        if card.get('phone'):
            r['phones'] = [card['phone']]
        if card.get('email'):
            r['best_for_outreach'] = card['email']
        return r
    if not site.startswith('http'):
        site = 'http://' + site
    r['site'] = _domain(site)
    r['site_source'] = src
    time.sleep(_PACE(*pace))
    _t0 = time.time()
    text, pages, err, csrc = crawl_contacts(site, pace)
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
    for e in emails:
        e['mx_ok'] = mx_ok(e.get('email', ''))
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
        companies = []
        for i in todo_inns:
            bi = idx.get(str(i), {})
            companies.append(dict(inn=str(i), name=bi.get('name', ''), city=bi.get('city', ''),
                                  phones=bi.get('phones', []), base_site=bi.get('site', '')))
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
    _DOLPHIN_TOKEN = args.get('dolphin_token', '') or ''
    _DOLPHIN_PROFILES = args.get('dolphin_profiles', []) or []
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
                    _db.upsert_company(
                        inn, name=r.get('name') or src.get('name'),
                        division=div or None,
                        okved=src.get('okved'), region=src.get('city') or src.get('region'),
                        pxr=src.get('pxr'), site=r.get('site'), activity=r.get('activity'),
                        is_competitor=r.get('is_competitor'), verified=r.get('verified'),
                        best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                    for e in (r.get('emails') or []):
                        _db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                      person=e.get('person', ''), mx_ok=e.get('mx_ok'),
                                      source=args.get('source') or 'enrich')
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
