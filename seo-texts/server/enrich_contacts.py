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
_SEM_XMLRIVER = threading.Semaphore(10)  # xmlriver лимит 10 яндекс-потоков — не превышаем

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
    try:
        with _SEM_XMLRIVER:
            xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, f'xmlriver-err:{str(e)[:40]}', {}
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
        return '', [], f'site-block:{meta.get("captcha_type") or method}'
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
    # JS-email: если в сыром HTML email НЕТ, он мог отрисоваться скриптом — рендерим
    # главную в браузере (Playwright исполнит JS) и дораскладываем текст.
    if not EMAIL_RE.search(txt) and not _NO_BROWSER:
        try:
            import browser_probe as BP
            with _SEM_BROWSER:
                out = BP.probe({'url': site, 'return_html': True, 'html_cap': 130000,
                                'wait_ms': 5000, 'screenshot': False, 'solve': True})
            if out.get('captcha_solved') or out.get('cf_solved'):
                _bump('twocaptcha' if out.get('captcha_type') == 'smartcaptcha' else 'capmonster')
            btxt = (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', out.get('html') or '')
            txt = re.sub(r'\s+', ' ', txt + ' ' + btxt)
        except Exception:  # noqa: BLE001
            pass
    return txt[:28000], pages, None


def extract_roles(text, company):
    """Провайдер: email С РОЛЯМИ + ЛПР для холодного письма. Фолбэк — regex."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    if key and EMAIL_RE.search(text):
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
    # regex-фолбэк: просто список email без ролей
    emails = sorted(set(e.lower() for e in EMAIL_RE.findall(text)
                        if not e.lower().endswith(('.png', '.jpg', '.gif', '.webp'))))
    return {'emails': [{'email': e, 'role': 'общий', 'person': ''} for e in emails[:8]],
            'phones': [], 'best_for_outreach': emails[0] if emails else ''}, 'regex'


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
    text, pages, err = crawl_contacts(site, pace)
    tmr['crawl'] = round(time.time() - _t0, 1)
    if err:
        r['timings'] = tmr
        r['error'] = err
        return r
    _t0 = time.time()
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


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    companies = args.get('companies', [])
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
    workers = max(1, min(int(args.get('workers', 6)), 24))
    # управление параллелизмом (сервер мощный → можно поднять)
    global _NO_BROWSER, _SEM_BROWSER, _USE_FALLBACK
    _NO_BROWSER = bool(args.get('no_browser', False))
    _USE_FALLBACK = not bool(args.get('no_fallback', False))
    bw = max(1, min(int(args.get('browser_workers', 2)), 30))
    _SEM_BROWSER = threading.Semaphore(bw)

    def _one(c):
        try:
            return enrich_one(c, pace)
        except Exception as e:  # noqa: BLE001
            return {'inn': c.get('inn'), 'name': c.get('name'), 'error': f'exc:{str(e)[:80]}'}

    # Параллельно МЕЖДУ компаниями (у каждой свой сайт). Discovery по общим хостам
    # (list-org/поисковик) сериализован семафором внутри enrich_one — один сайт не грузим.
    if workers > 1 and len(companies) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_one, companies))
    else:
        results = [_one(c) for c in companies]
    # write-through в единое хранилище (система-источник-истины), идемпотентно по ИНН
    if args.get('write_db', True):
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
            cin = {str(c.get('inn')): c for c in companies if c.get('inn')}
            for r in results:
                inn = str(r.get('inn') or '')
                if not inn:
                    continue
                src = cin.get(inn, {})
                db.upsert_company(
                    inn, name=r.get('name') or src.get('name'),
                    division=src.get('division') or args.get('division'),
                    okved=src.get('okved'), region=src.get('city') or src.get('region'),
                    pxr=src.get('pxr'), site=r.get('site'), activity=r.get('activity'),
                    is_competitor=r.get('is_competitor'), verified=r.get('verified'),
                    best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                for e in (r.get('emails') or []):
                    db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                 person=e.get('person', ''), mx_ok=e.get('mx_ok'),
                                 source=args.get('source') or 'enrich')
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'enrich_db write skip: {str(e)[:100]}\n')
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
