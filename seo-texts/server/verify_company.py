# -*- coding: utf-8 -*-
"""Задача раннера: проверка реквизитов компаний с РФ-IP сервера.

Вход (stdin JSON): {"companies":[{"name":..,"inn":..,"city":..}, ...],
                    "source":"checko"|"rusprofile" (опц., по умолч. checko)}
Выход (stdout JSON): {"results":[{name, inn, full_name, address, region,
                     revenue, revenue_year, status, okved, source_url,
                     method, error?}, ...]}

Логика: сервер (РФ-IP) тянет страницу источника; при Cloudflare-челлендже —
решает Turnstile через CapMonster (ключ CAPMONSTER_KEY); затем HTML отдаётся
провайдеру (claude-fable-5) для извлечения реквизитов (устойчиво к вёрстке).
Тяжёлый парсинг — через провайдер (правило владельца). stdlib + опц. gen_provider.

ЗАМЕТКА для боевой настройки на сервере: путь cf_clearance (обмен токена
Turnstile на куку доступа) site-specific; проверить и при необходимости
подкрутить _fetch на реальном сервере, где сайты реально открываются.
"""
import os
import sys
import json
import time
import re
import random
import urllib.request
import urllib.error
import urllib.parse

# темп запросов (антибот по частоте) — переопределяется из args в main()
_PACE_MIN = 6.0
_PACE_MAX = 14.0


def _PACE():
    return random.uniform(_PACE_MIN, _PACE_MAX)

CAPMONSTER_KEY = os.environ.get('CAPMONSTER_KEY', '')
CAP_BASE = 'https://api.capmonster.cloud'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# таймаут GET сайта: дефолт 45с для одиночной верификации; массовый прогон ставит ниже
# (мёртвые сайты не должны держать воркер по 45-90с). enrich_contacts main() переопределит.
_FETCH_TIMEOUT = 45

# Мобильный прокси (по желанию владельца): маршрутизируем ВСЕ urllib-запросы процесса
# через него — server-IP датацентра ловит WinError 10060 на DuckDuckGo и баны на list-org.
# ОДИН статичный IP блокируется под объёмом (проверено: 54 компании -> 403/пусто), поэтому
# берём ПУЛ и на КАЖДЫЙ job (subprocess) ставим СЛУЧАЙНЫЙ IP из пула — прогоняем 54 батчами,
# каждый батч с другого IP. Источник пула (для массового краула нужна ротация):
#   PROXY_URLV2 (список asocks .txt, много IP) -> PROXY_URLV3 (http, 1 IP) -> PROXY_URL.
# http — ProxyHandler (нативно); socks5 — через PySocks (если стоит на сервере).
import random as _random
PROXY_OK = False
PROXY_MODE = 'none'
PROXY_POOL = []


def _fetch_list(u):
    """http(s)-ссылка на список прокси (.txt asocks) -> список строк; иначе [u]."""
    try:
        p = urllib.parse.urlsplit(u)
        if p.scheme in ('http', 'https') and (p.path.endswith('.txt') or 'list' in (p.netloc + p.path)):
            body = urllib.request.urlopen(u, timeout=25).read().decode('utf-8', 'replace')
            return [ln.strip() for ln in body.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []
    return [u]


def _build_pool():
    v2 = os.environ.get('PROXY_URLV2', '').strip()
    if v2:
        lst = _fetch_list(v2)
        if lst:
            return lst
    for var in ('PROXY_URLV3', 'PROXY_URL'):
        v = os.environ.get(var, '').strip()
        if v:
            return [v]
    return []


def _install_one(u):
    global PROXY_OK, PROXY_MODE
    p = urllib.parse.urlsplit(u if '://' in u else 'http://' + u)
    if p.scheme in ('http', 'https'):
        try:
            urllib.request.install_opener(urllib.request.build_opener(
                urllib.request.ProxyHandler({'http': u, 'https': u})))
            PROXY_OK, PROXY_MODE = True, f'http(пул={len(PROXY_POOL)})'
        except Exception as e:  # noqa: BLE001
            PROXY_MODE = f'http-fail:{e.__class__.__name__}'
    elif p.scheme.startswith('socks'):
        try:
            import socks  # PySocks
            from sockshandler import SocksiPyHandler
            urllib.request.install_opener(urllib.request.build_opener(SocksiPyHandler(
                socks.SOCKS5, p.hostname, p.port or 1080,
                username=p.username, password=p.password, rdns=True)))
            PROXY_OK, PROXY_MODE = True, f'socks5(пул={len(PROXY_POOL)})'
        except ImportError:
            PROXY_MODE = 'socks-need-PySocks'
        except Exception as e:  # noqa: BLE001
            PROXY_MODE = f'socks-fail:{e.__class__.__name__}'


PROXY_POOL = _build_pool()
if PROXY_POOL:
    try:
        _install_one(_random.choice(PROXY_POOL))
    except Exception:  # noqa: BLE001
        pass

SOURCES = {
    'checko': 'https://checko.ru/search?query={q}',
    'rusprofile': 'https://www.rusprofile.ru/search?query={q}',
}


# ---------------------------------------------------------------- provider
def _load_provider():
    """Пытаемся импортировать gen_provider (парс реквизитов). Не жёсткая зависимость."""
    for cand in (os.environ.get('PROVIDER_CLIENT_DIR'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'),
                 r'C:\sender', os.path.dirname(os.path.abspath(__file__))):
        if cand and os.path.isdir(cand) and os.path.exists(os.path.join(cand, 'gen_provider.py')):
            if cand not in sys.path:
                sys.path.insert(0, cand)
            try:
                import gen_provider  # type: ignore
                return gen_provider
            except Exception:  # noqa: BLE001
                continue
    return None


GP = _load_provider()


# модель extract_roles: haiku на массовый вал (9× дешевле fable, качество ~90%, проверено).
# Настраивается per-job (enrich_contacts ставит из args.extract_model) или env PROVIDER_MODEL.
_PROVIDER_MODEL = os.environ.get('PROVIDER_MODEL', 'claude-fable-5')


def _provider_call_stdlib(prompt, model=None):
    """Вызов провайдерского API чисто на urllib (без httpx/gen_provider).
    Заголовок User-Agent: curl/8.5.0 — пройти WAF шлюза (как в gen_provider).
    Возвращает текст ответа или None."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    if not key:
        return None
    body = json.dumps({'model': model or _PROVIDER_MODEL, 'max_tokens': 1500,
                       'messages': [{'role': 'user', 'content': prompt}]}).encode('utf-8')
    req = urllib.request.Request(
        base + '/v1/messages', data=body, method='POST',
        headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json', 'User-Agent': 'curl/8.5.0'})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    parts = data.get('content') or []
    return ''.join(p.get('text', '') for p in parts if p.get('type') == 'text') or None


def extract_via_provider(html, company):
    if GP is None and not os.environ.get('PROVIDER_API_KEY'):
        return None
    # режем html до вменяемого размера: берём текстовую выжимку
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)[:24000]
    prompt = (
        'Из текста страницы карточки компании извлеки реквизиты. Компания-цель: '
        f'{company.get("name","")} ИНН {company.get("inn","") or "неизвестен"} '
        f'город {company.get("city","")}. Верни СТРОГО JSON без markdown: '
        '{"inn":"","full_name":"","address":"","region":"","revenue":число_руб_или_null,'
        '"revenue_year":"","status":"","okved":""}. Если данных нет — пустая строка/null. '
        'Бери ПОСЛЕДНИЙ доступный год выручки. Текст:\n' + text)
    for _ in range(3):
        try:
            if GP is not None:
                msg = GP._raw_stream([{'role': 'user', 'content': prompt}],
                                     'claude-fable-5', 800, thinking=False)
                out = ''.join(b.text for b in msg.content
                              if getattr(b, 'type', '') == 'text')
            else:
                out = _provider_call_stdlib(prompt) or ''
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            time.sleep(1.5)
    return None


# ------------------------------------------------------------- capmonster
def _cap_post(path, payload):
    req = urllib.request.Request(
        f'{CAP_BASE}/{path}', data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def solve_turnstile(site_url, site_key):
    """Решить Cloudflare Turnstile через CapMonster -> (token, user_agent) | (None,None)."""
    if not CAPMONSTER_KEY or not site_key:
        return None, None
    try:
        created = _cap_post('createTask', {
            'clientKey': CAPMONSTER_KEY,
            'task': {'type': 'TurnstileTask', 'websiteURL': site_url,
                     'websiteKey': site_key}})
        task_id = created.get('taskId')
        if not task_id:
            return None, None
        for _ in range(24):  # до ~2 мин
            time.sleep(5)
            res = _cap_post('getTaskResult',
                            {'clientKey': CAPMONSTER_KEY, 'taskId': task_id})
            if res.get('status') == 'ready':
                sol = res.get('solution', {})
                return sol.get('token'), sol.get('userAgent')
    except Exception:  # noqa: BLE001
        return None, None
    return None, None


def _sitekey(body):
    for pat in (r'data-sitekey="([^"]+)"', r'data-sitekey=\'([^\']+)\'',
                r'sitekey["\s:=]+([A-Za-z0-9_\-]{8,})',
                r'render=([A-Za-z0-9_\-]{20,})'):
        m = re.search(pat, body or '')
        if m:
            return m.group(1)
    return None


def _detect_block(status, body):
    """Определить, заблокирован ли ответ и ЧЕМ. Возвращает (kind, sitekey).
    kind: None (чисто) | 'cloudflare' | 'smartcaptcha' | 'recaptcha' |
          'rate-limit-429' | 'unknown-block'. Диагностика под неизвестную капчу."""
    b = (body or '').lower()
    # маркеры конкретных капч проверяем ПЕРВЫМИ — checko/list-org отдают
    # human-check вместе со статусом 429, поэтому 429 не должен перебивать тип.
    if 'smartcaptcha' in b or 'captcha-api.yandex' in b or 'ysc1_' in b:
        return 'smartcaptcha', _sitekey(body)
    if 'g-recaptcha' in b or 'recaptcha/api.js' in b or 'grecaptcha' in b:
        return 'recaptcha', _sitekey(body)
    if ('just a moment' in b or 'cf-challenge' in b or 'cf_chl' in b
            or 'challenge-platform' in b or 'cf-turnstile' in b):
        return 'cloudflare', _sitekey(body)
    # РУ-антибот по фразам (checko: «подтвердите, что вы человек»;
    # list-org: «Проверка, что Вы не робот», «слишком часто обращались»)
    if ('подтвердите' in b or 'вы человек' in b or 'не робот' in b
            or 'слишком часто' in b or ('проверка' in b and 'робот' in b)
            or 'вы не робот' in b):
        return 'human-check', _sitekey(body)
    if status == 429 or '429 too many requests' in b:
        return 'rate-limit-429', None
    if status in (403, 503):
        return 'blocked-http', _sitekey(body)
    if len(body or '') < 3000 and ('captcha' in b or 'проверя' in b or 'robot' in b):
        return 'unknown-block', _sitekey(body)
    return None, None


def _is_challenge(status, body):
    kind, _ = _detect_block(status, body)
    return kind == 'cloudflare'


def _norm_url(u):
    """Нормализовать URL с не-ASCII (домены .рф, кириллические пути) — иначе urllib
    падает 'latin-1 codec can't encode'. IDNA-хост + percent-энкод пути/запроса."""
    try:
        from urllib.parse import urlsplit, urlunsplit, quote
        p = urlsplit(u)
        host = p.hostname or ''
        try:
            host_a = host.encode('idna').decode('ascii')
        except Exception:  # noqa: BLE001
            host_a = host
        netloc = host_a + (f':{p.port}' if p.port else '')
        if p.username:
            cred = p.username + (f':{p.password}' if p.password else '') + '@'
            netloc = cred + netloc
        path = quote(p.path, safe="/%:@!$&'()*+,;=~")
        query = quote(p.query, safe="=&%:/?@!$'()*+,;~")
        return urlunsplit((p.scheme, netloc, path, query, p.fragment))
    except Exception:  # noqa: BLE001
        return u


def _fetch(url):
    """GET с браузерными заголовками; при Cloudflare-челлендже — CapMonster Turnstile.
    Возвращает (html, method, meta). method: 'direct' | 'capmonster' |
    'challenge-unsolved' | 'blocked:<kind>' | 'error:...'. meta несёт диагностику
    блокировки (captcha_type, sitekey, http_status, snippet) для неизвестной капчи."""
    url = _norm_url(url)
    headers = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
               'Accept': 'text/html,application/xhtml+xml'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as r:
            try:
                raw = r.read()
            except Exception as re_:  # noqa: BLE001  IncompleteRead: берём частичное
                raw = getattr(re_, 'partial', b'') or b''
            body = raw.decode('utf-8', 'replace')
            status = r.status
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            body = ''
        status = e.code
    except Exception as e:  # noqa: BLE001
        # частичный HTML мог быть прочитан до обрыва
        part = getattr(e, 'partial', b'')
        if part:
            return part.decode('utf-8', 'replace'), 'direct', {'http_status': None}
        return None, f'error:{str(e)[:60]}', {'http_status': None}

    kind, sitekey = _detect_block(status, body)
    if kind is None:
        return body, 'direct', {'http_status': status}

    meta = {'captcha_type': kind, 'sitekey': sitekey, 'http_status': status,
            'snippet': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body or ''))[:280]}

    # только Cloudflare-Turnstile умеем решать сейчас; остальное — диагностируем
    if kind != 'cloudflare':
        return body, f'blocked:{kind}', meta

    token, ua = solve_turnstile(url, sitekey)
    if not token:
        return body, 'challenge-unsolved', meta
    # повтор с решённым токеном и его user-agent. Полный обмен токена на куку
    # cf_clearance site-specific — при недоборе доводится на боевом сервере.
    try:
        h2 = dict(headers)
        h2['User-Agent'] = ua or UA
        h2['cf-turnstile-response'] = token
        with urllib.request.urlopen(urllib.request.Request(url, headers=h2), timeout=45) as r:
            body2 = r.read().decode('utf-8', 'replace')
        k2, _ = _detect_block(200, body2)
        return (body2, 'capmonster', meta) if k2 is None else (body2, 'challenge-unsolved', meta)
    except Exception as e:  # noqa: BLE001
        return body, f'capmonster-retry-failed:{str(e)[:40]}', meta


def _num(s):
    s = re.sub(r'[^\d]', '', s or '')
    return int(s) if s else None


def extract_regex(html, source=''):
    """Извлечь реквизиты регэкспом из HTML (данные у list-org/sbis/zachestny —
    прямо в разметке, LLM не нужен). Возвращает dict полей или {}."""
    if not html:
        return {}
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;?', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    d = {}
    m = re.search(r'ИНН[:\s]*?(\d{10,12})', text)
    if m: d['inn'] = m.group(1)
    m = re.search(r'(?:Полное наименование|Полное название|Организация)[:\s]*'
                  r'([«"А-ЯЁ][^\n]{5,140}?)(?:ИНН|ОГРН|Дата|Юридический|Статус|$)', text)
    if m: d['full_name'] = m.group(1).strip(' .,')
    m = re.search(r'(?:Юридический адрес|Адрес(?: регистрации)?|Место нахождения)'
                  r'[:\s]*(\d{6},?\s*[^\n]{8,140}?)(?:Дата|ОКВЭД|Статус|Телефон|Руковод|E-?mail|$)', text)
    if m: d['address'] = re.sub(r'\s+', ' ', m.group(1)).strip(' .,')
    # выручка: берём последнее/наибольшее число рядом со словом «выручка»
    revs = []
    for mm in re.finditer(r'[Вв]ыручка[^\d]{0,60}?([\d][\d  \xa0.,]{2,})\s*(тыс|млн|млрд)?', text):
        val = _num(mm.group(1)); unit = (mm.group(2) or '').lower()
        if val is None: continue
        mult = {'тыс': 1_000, 'млн': 1_000_000, 'млрд': 1_000_000_000}.get(unit, 1)
        revs.append(val * mult)
    if revs: d['revenue'] = max(revs)
    m = re.search(r'([Дд]ействующ\w+|[Лл]иквидир\w+|[Бб]анкрот\w*|[Вв] стадии ликвидации|[Пп]рекратил\w+)', text)
    if m: d['status'] = m.group(1)
    m = re.search(r'ОКВЭД[:\s]*(\d{2}(?:\.\d{1,2}){0,2})', text)
    if m: d['okved'] = m.group(1)
    m = re.search(r'([А-Яа-яё\-]+(?:ская|ский| край|область|Республика[^,]{0,20}|округ)[^,\n]{0,25})', text)
    if m and 'address' in d: d['region'] = m.group(1).strip()
    return {k: v for k, v in d.items() if v}


def _resolve_url(company, source):
    """URL(ы) для источника. list-org требует 2 шага (поиск→карточка); остальные
    прямые. Возвращает список URL для последовательного обхода."""
    q = company.get('inn') or f"{company.get('name','')} {company.get('city','')}".strip()
    qe = urllib.parse.quote(q)
    if source == 'list-org':
        return [f'https://www.list-org.com/search?type=inn&val={qe}']
    return [SOURCES.get(source, SOURCES['checko']).format(q=qe)]


def verify_one(company, source):
    urls = _resolve_url(company, source)
    url = urls[0]
    html, method, meta = _fetch(url)
    # list-org: с поисковой выдачи берём id карточки и догружаем её
    if source == 'list-org' and html and not meta.get('captcha_type'):
        ids = re.findall(r'/company/(\d+)', html)
        if ids:
            time.sleep(_PACE())
            url2 = f'https://www.list-org.com/company/{ids[0]}'
            h2, m2, meta2 = _fetch(url2)
            if h2 and not meta2.get('captcha_type'):
                html, method, meta, url = h2, m2, meta2, url2
    base = {'name': company.get('name'), 'inn_query': company.get('inn'),
            'source_url': url, 'method': method}
    # диагностика блокировки/капчи — чтобы понять тип защиты источника
    if meta.get('captcha_type'):
        base['captcha_type'] = meta.get('captcha_type')
        base['sitekey'] = meta.get('sitekey')
        base['http_status'] = meta.get('http_status')
        base['snippet'] = meta.get('snippet')
    if (not html or method in ('challenge-unsolved',)
            or method.startswith('error') or method.startswith('blocked')
            or method.startswith('capmonster-retry-failed')):
        base['error'] = f'fetch не удался ({method})'
        return base
    # регэксп-первый (данные в HTML → без LLM); провайдер — фолбэк, если доступен
    data = extract_regex(html, source)
    have_provider = GP is not None or bool(os.environ.get('PROVIDER_API_KEY'))
    if not all(data.get(k) for k in ('address', 'revenue', 'full_name')) and have_provider:
        pdata = extract_via_provider(html, company)
        if pdata:
            # провайдер полнее — берём его, регэксп-поля как подстраховка
            data = {**data, **{k: v for k, v in pdata.items() if v}}
            base['extract'] = 'provider'
        else:
            base['extract'] = 'regex'
    else:
        base['extract'] = 'regex'
    base.update({k: data.get(k) for k in
                 ('inn', 'full_name', 'address', 'region', 'revenue',
                  'revenue_year', 'status', 'okved')})
    if not any(base.get(k) for k in ('address', 'revenue', 'full_name')):
        base['error'] = 'реквизиты не извлечены (проверить селекторы источника)'
    return base


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    companies = args.get('companies', [])
    source = args.get('source', 'checko')
    # темп по-человечески (антибот по частоте); можно переопределить из args
    global _PACE_MIN, _PACE_MAX
    _PACE_MIN = float(args.get('pace_min', 6.0))
    _PACE_MAX = float(args.get('pace_max', 14.0))
    cooldown = float(args.get('cooldown_sec', 90.0))  # пауза при блоке
    results = []
    for i, c in enumerate(companies):
        try:
            r = verify_one(c, source)
        except Exception as e:  # noqa: BLE001
            r = {'name': c.get('name'), 'error': f'exc:{str(e)[:80]}'}
        results.append(r)
        # при блоке/капче — длинная пауза (остыть), иначе человеческий интервал
        blocked = r.get('captcha_type') or str(r.get('method', '')).startswith(('blocked', 'challenge'))
        if i < len(companies) - 1:
            time.sleep(cooldown if blocked else _PACE())
    # сводка по методам и типам капчи — быстрый диагноз защиты источника
    from collections import Counter
    methods = Counter(r.get('method', '?') for r in results)
    captchas = Counter(r.get('captcha_type') for r in results if r.get('captcha_type'))
    got_data = sum(1 for r in results if r.get('revenue') or r.get('address'))
    json.dump({'results': results, 'count': len(results),
               'summary': {'methods': dict(methods), 'captcha_types': dict(captchas),
                           'with_data': got_data},
               'capmonster': bool(CAPMONSTER_KEY), 'provider': GP is not None},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
