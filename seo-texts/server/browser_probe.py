# -*- coding: utf-8 -*-
"""Браузерный пробник (Playwright): рендерит URL в Chromium (проходит JS-антибот),
диагностирует — отрендерились ли ДАННЫЕ или всплыла КАПЧА (тип+sitekey), делает
скрин и кладёт его на дроп. Для checko и любых SPA/капча-источников.

stdin: {"url":"https://checko.ru/company/...","inn":"","ogrn":"","screenshot":true,
        "wait_ms":6000,"headful":false}
stdout: {"url","title","http_status","captcha_type","sitekey","data_found",
         "text_snippet","screenshot_drop","error?"}
Требует: pip install playwright && playwright install chromium (на сервере)."""
import os, sys, json, re, time
import urllib.request, urllib.parse


def _parse_proxy(url):
    """socks5://user:pass@host:port или http://... -> dict для Playwright и 2captcha | None."""
    if not url:
        return None
    try:
        p = urllib.parse.urlsplit(url if '://' in url else 'http://' + url)
        if not p.hostname:
            return None
        sch = p.scheme or 'http'
        port = p.port or (443 if sch == 'https' else 1080 if sch.startswith('socks') else 80)
        return {'scheme': sch, 'host': p.hostname, 'port': port,
                'username': p.username, 'password': p.password or '',
                'server': f'{sch}://{p.hostname}:{port}'}
    except Exception:  # noqa: BLE001
        return None


def _pick_proxy(args, prefer='static'):
    """Выбрать прокси по роли. static (по умолч.) -> PROXY_URL сперва (статичный IP для
    привязки капча-токена), затем PROXY_URLV2. rotating -> наоборот (ротация для массового
    краула). {"proxy":false} отключает. {"proxy_var":"PROXY_URLV2"} — форсить конкретный."""
    if not args.get('proxy', True):
        return None
    var = args.get('proxy_var')
    # V3 (http) первым для БРАУЗЕРА: Chromium умеет http-авторизацию, а socks-авторизацию
    # НЕ умеет. Дальше статичный socks и список.
    order = [var] if var else (['PROXY_URLV3', 'PROXY_URL', 'PROXY_URLV2'] if prefer == 'static'
                               else ['PROXY_URLV2', 'PROXY_URLV3', 'PROXY_URL'])
    for k in order:
        p = _parse_proxy(os.environ.get(k, ''))
        if p:
            p['var'] = k
            return p
    return None

DIR = os.path.dirname(os.path.abspath(__file__))
DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')

CAPTCHA_MARKERS = {
    'smartcaptcha': ('smartcaptcha', 'captcha-api.yandex', 'ysc1_'),
    'recaptcha': ('g-recaptcha', 'recaptcha/api.js', 'grecaptcha'),
    'cloudflare': ('cf-turnstile', 'challenge-platform', 'just a moment', 'cf-chl'),
    'human-check': ('подтвердите, что вы человек', 'вы не робот', 'проверка, что вы',
                    'слишком часто'),
}


def _detect(html):
    b = (html or '').lower()
    for kind, marks in CAPTCHA_MARKERS.items():
        if any(m in b for m in marks):
            sk = re.search(r'(?:data-sitekey|sitekey)["\s:=]+([A-Za-z0-9_\-]{8,})', html or '')
            return kind, (sk.group(1) if sk else None)
    return None, None


def _drop_up(name, blob):
    req = urllib.request.Request(f'{DROP_URL}/{name}', data=blob, method='PUT',
                                 headers={'X-Drop-Token': DROP_TOKEN})
    urllib.request.urlopen(req, timeout=90).read()


CAP_BASE = 'https://api.capmonster.cloud'


def _cap_post(path, payload):
    req = urllib.request.Request(f'{CAP_BASE}/{path}', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def solve_recaptcha_v2(url, sitekey):
    """Решить reCAPTCHA v2 через CapMonster -> g-recaptcha-response токен | None."""
    key = os.environ.get('CAPMONSTER_KEY', '')
    if not key or not sitekey:
        return None
    try:
        r = _cap_post('createTask', {'clientKey': key, 'task': {
            'type': 'RecaptchaV2TaskProxyless', 'websiteURL': url, 'websiteKey': sitekey}})
        tid = r.get('taskId')
        if not tid:
            return None
        for _ in range(24):  # до ~2 мин
            time.sleep(5)
            res = _cap_post('getTaskResult', {'clientKey': key, 'taskId': tid})
            if res.get('status') == 'ready':
                return (res.get('solution') or {}).get('gRecaptchaResponse')
    except Exception:  # noqa: BLE001
        return None
    return None


# Перехватчик turnstile.render — внедряется до загрузки challenge-скрипта Cloudflare.
# Cloudflare сам присваивает window.turnstile ПОСЛЕ старта страницы, поэтому вешаем
# сеттер на window.turnstile: как только CF его установит — оборачиваем .render в Proxy
# и при первом вызове снимаем sitekey/cData/chlPageData/action/callback (нужны CapMonster).
_CF_INIT_JS = r"""
(() => {
  window.__cf_params = null; window.__cf_cb = null;
  let _t;
  try {
    Object.defineProperty(window, 'turnstile', {
      configurable: true,
      get(){ return _t; },
      set(v){
        try {
          _t = new Proxy(v, {
            get(target, prop){
              if (prop === 'render') {
                return function(a, b){
                  try {
                    window.__cf_params = {
                      websiteKey: b.sitekey,
                      websiteURL: location.href,
                      data: b.cData,
                      pagedata: b.chlPageData,
                      action: b.action,
                      userAgent: navigator.userAgent
                    };
                    window.__cf_cb = b.callback;
                  } catch(e){}
                  return target.render.apply(this, arguments);
                };
              }
              return target[prop];
            }
          });
        } catch(e){ _t = v; }
      }
    });
  } catch(e){}
})();
"""


def solve_cloudflare_challenge(page):
    """Пройти Cloudflare Challenge («Один момент»/«Just a moment») через CapMonster
    TurnstileTask (cloudflareTaskType=token, встроенные прокси — свой прокси НЕ нужен).
    Требует внедрённого _CF_INIT_JS до goto. Возвращает True, если токен получен и внедрён.

    Логика: ждём, пока challenge-скрипт вызовет turnstile.render и перехватчик снимет
    параметры в window.__cf_params -> createTask -> getTaskResult -> solution.token ->
    вызываем callback challenge'а (или заполняем cf-turnstile-response) -> ждём навигацию."""
    key = os.environ.get('CAPMONSTER_KEY', '')
    if not key:
        return False

    def _scan_params():
        # turnstile.render в managed-challenge вызывается ВНУТРИ дочернего фрейма
        # challenges.cloudflare.com — проверяем главный фрейм И все дочерние.
        for fr in [page] + list(page.frames):
            try:
                pr = fr.evaluate('window.__cf_params')
            except Exception:  # noqa: BLE001
                pr = None
            if pr and pr.get('websiteKey'):
                return pr, fr
        return None, None

    params, frame = None, page
    for _ in range(40):  # до ~20с ждём перехвата turnstile.render
        params, frame = _scan_params()
        if params:
            break
        page.wait_for_timeout(500)
    if not params or not params.get('websiteKey'):
        return False
    task = {'type': 'TurnstileTask',
            'websiteURL': params.get('websiteURL') or page.url,
            'websiteKey': params.get('websiteKey'),
            'cloudflareTaskType': 'token',
            'userAgent': params.get('userAgent') or UA}
    if params.get('action'):
        task['pageAction'] = params['action']
    if params.get('pagedata'):
        task['pageData'] = params['pagedata']
    if params.get('data'):
        task['data'] = params['data']
    try:
        r = _cap_post('createTask', {'clientKey': key, 'task': task})
        tid = r.get('taskId')
        if not tid:
            return False
        token = None
        for _ in range(36):  # до ~3 мин
            time.sleep(5)
            res = _cap_post('getTaskResult', {'clientKey': key, 'taskId': tid})
            if res.get('status') == 'ready':
                token = (res.get('solution') or {}).get('token')
                break
            if res.get('errorId'):
                return False
        if not token:
            return False
        # внедряем токен в ТОТ фрейм, где перехватили render (callback живёт там же)
        inject = (
            "(t)=>{try{if(typeof window.__cf_cb==='function'){window.__cf_cb(t);}}catch(e){}"
            "try{document.querySelectorAll("
            "'[name=\"cf-turnstile-response\"],#cf-chl-widget-response,"
            "input[name=\"g-recaptcha-response\"]').forEach(e=>{e.value=t;});}catch(e){}}")
        try:
            (frame or page).evaluate(inject, token)
        except Exception:  # noqa: BLE001
            page.evaluate(inject, token)
        # challenge обычно сабмитит форму сам по callback; ждём ухода со страницы-заглушки
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(6000)
        return True
    except Exception:  # noqa: BLE001
        return False


# --- 2captcha: Yandex SmartCaptcha (у CapMonster нативного Yandex-таска НЕТ; берём то,
# что капмонстр не умеет, через 2captcha — по указанию владельца). Ключ: TWOCAPTCHA_KEY
# в runner-secrets.env на сервере (НЕ в чат/гит). Прокси не нужен (пул 2captcha). ---
TWOCAP_BASE = 'https://api.2captcha.com'


def _twocap_key():
    return os.environ.get('TWOCAPTCHA_KEY', '') or os.environ.get('RUCAPTCHA_KEY', '')


def _2cap_post(path, payload):
    req = urllib.request.Request(f'{TWOCAP_BASE}/{path}', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def solve_yandex_smartcaptcha(url, sitekey, prox=None):
    """Решить Yandex SmartCaptcha через 2captcha -> smart-token | None.
    Если передан prox — решаем ЧЕРЕЗ наш прокси (YandexSmartCaptchaTask), чтобы токен был
    валиден для НАШЕГО IP (у яндекс-антиробота токен привязан к IP); тот же IP, что и в
    браузере. Без прокси — Proxyless (пул 2captcha)."""
    key = _twocap_key()
    if not key or not sitekey:
        return None
    task = {'websiteURL': url, 'websiteKey': sitekey}
    if prox and prox.get('host'):
        task['type'] = 'YandexSmartCaptchaTask'
        task['proxyType'] = prox['scheme']
        task['proxyAddress'] = prox['host']
        task['proxyPort'] = prox['port']
        if prox.get('username'):
            task['proxyLogin'] = prox['username']
            task['proxyPassword'] = prox['password']
    else:
        task['type'] = 'YandexSmartCaptchaTaskProxyless'
    try:
        r = _2cap_post('createTask', {'clientKey': key, 'task': task})
        tid = r.get('taskId')
        if not tid:
            return None
        for _ in range(36):  # до ~3 мин
            time.sleep(5)
            res = _2cap_post('getTaskResult', {'clientKey': key, 'taskId': tid})
            if res.get('status') == 'ready':
                return (res.get('solution') or {}).get('token')
            if res.get('errorId'):
                return None
    except Exception:  # noqa: BLE001
        return None
    return None


# Перехватчик smartCaptcha.render — снимает sitekey и callback Yandex SmartCaptcha
# (аналогично turnstile). Yandex присваивает window.smartCaptcha после старта.
_YSC_INIT_JS = r"""
(() => {
  window.__ysc_params = null; window.__ysc_cb = null;
  let _s;
  try {
    Object.defineProperty(window, 'smartCaptcha', {
      configurable: true,
      get(){ return _s; },
      set(v){
        try {
          _s = new Proxy(v, {
            get(target, prop){
              if (prop === 'render') {
                return function(cont, params){
                  try {
                    window.__ysc_params = { sitekey: (params||{}).sitekey, websiteURL: location.href };
                    window.__ysc_cb = (params||{}).callback;
                  } catch(e){}
                  return target.render.apply(this, arguments);
                };
              }
              return target[prop];
            }
          });
        } catch(e){ _s = v; }
      }
    });
  } catch(e){}
})();
"""


def _ysc_sitekey(page, fallback):
    """sitekey Yandex SmartCaptcha: detect-регекс -> перехват render (все фреймы) ->
    парсинг HTML/iframe-src (sitekey=...) как последний фолбэк."""
    if fallback:
        return fallback
    # 1) перехваченный smartCaptcha.render в любом фрейме
    for fr in [page] + list(page.frames):
        try:
            k = fr.evaluate('(window.__ysc_params||{}).sitekey')
        except Exception:  # noqa: BLE001
            k = None
        if k:
            return k
    # 2) распарсить из HTML (виджет/iframe хранят sitekey в конфиге или query)
    try:
        html = page.content()
    except Exception:  # noqa: BLE001
        html = ''
    for pat in (r'[?&]sitekey=([A-Za-z0-9_\-]{10,})',
                r'["\']sitekey["\']\s*[:=]\s*["\']([A-Za-z0-9_\-]{10,})',
                r'data-sitekey=["\']([A-Za-z0-9_\-]{10,})'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


# --- Dolphin{anty} Local API: антидетект-профили (свой прокси+отпечаток) вместо сырого
# Chromium. Работает, пока запущено десктоп-приложение Dolphin на сервере. Токен —
# DOLPHIN_TOKEN в runner-secrets.env. Контракт как в корневом src/dolphin.mjs. ---
DOLPHIN_BASE = os.environ.get('DOLPHIN_API', 'http://localhost:3001/v1.0').rstrip('/')


def _dolphin_headers(token=None):
    h = {'Content-Type': 'application/json'}
    t = token or os.environ.get('DOLPHIN_TOKEN', '')
    if t:
        h['Authorization'] = 'Bearer ' + t
    return h


# Dolphin API ЛОКАЛЬНЫЙ (localhost:3001) — обращения ДОЛЖНЫ идти напрямую, минуя системный
# прокси раннера (иначе SOCKS «Connection not allowed by ruleset», инцидент 2026-07-23:
# dolphin_list возвращал 0, dolphin_start падал → дельфин не поднимался).
_DOLPHIN_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _dolphin_req(method, path, timeout=60, token=None):
    req = urllib.request.Request(f'{DOLPHIN_BASE}/{path.lstrip("/")}',
                                 headers=_dolphin_headers(token), method=method)
    with _DOLPHIN_OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read() or b'{}')


def dolphin_list(token=None):
    """Список профилей Dolphin: [{id,name}]. Пробуем разные формы ответа Local/Remote API."""
    for path in ('browser_profiles', 'browser_profiles?limit=100'):
        try:
            d = _dolphin_req('GET', path, token=token)
            items = d.get('data') or d.get('items') or (d if isinstance(d, list) else [])
            out = [{'id': str(x.get('id')), 'name': x.get('name', '')} for x in items if x.get('id')]
            if out:
                return out
        except Exception:  # noqa: BLE001
            continue
    return []


def dolphin_is_running(profile_id, token=None):
    """Профиль сейчас ЗАПУЩЕН? (Local API: /browser_profiles/{id} -> automation.port|active).
    True/False/None(не смогли узнать). Чтобы не стартовать уже открытый (EBUSY/дубль-окна)."""
    try:
        d = _dolphin_req('GET', f'browser_profiles/{profile_id}', timeout=10, token=token)
        au = (d or {}).get('automation') or {}
        if au.get('port'):
            return True
        st = str((d or {}).get('status') or (d or {}).get('state') or '').lower()
        if st in ('running', 'active', 'started'):
            return True
        return False
    except Exception:  # noqa: BLE001
        return None


def dolphin_start(profile_id, headless=False, token=None, skip_if_running=False):
    """Старт профиля -> CDP-эндпоинт для Playwright.connect_over_cdp | None.
    skip_if_running=True: если профиль УЖЕ запущен (вручную/др. джобом) -> RuntimeError
    'busy' вместо повторного старта (не плодим окна, наводка владельца).
    Иначе сначала stop (идемпотентно): освобождаем зависший с прошлого прогона слот."""
    if skip_if_running and dolphin_is_running(profile_id, token=token) is True:
        raise RuntimeError(f'profile {profile_id} busy (уже запущен)')
    dolphin_stop(profile_id, token=token)
    path = f'browser_profiles/{profile_id}/start?automation=1' + ('&headless=1' if headless else '')
    d = _dolphin_req('GET', path, token=token)
    auto = d.get('automation') or {}
    port = auto.get('port')
    if not port:
        raise RuntimeError(f'dolphin start fail: {json.dumps(d)[:150]}')
    ws = auto.get('wsEndpoint')
    return (f'ws://127.0.0.1:{port}{ws}' if ws else f'http://127.0.0.1:{port}'), port


def dolphin_stop(profile_id, token=None):
    try:
        _dolphin_req('GET', f'browser_profiles/{profile_id}/stop', timeout=30, token=token)
    except Exception:  # noqa: BLE001
        pass


def dolphin_close_tabs(browser):
    """Закрыть ВСЕ вкладки профиля перед стопом (наводка владельца): дельфин сохраняет сессию,
    и при следующем старте грузит все старые вкладки — теряется время. Оставляем одну чистую
    about:blank (чтобы окно не схлопнулось до dolphin_stop), остальные закрываем. Звать ПЕРЕД
    browser.close() + dolphin_stop."""
    try:
        ctxs = list(browser.contexts or [])
        keep = None
        if ctxs:
            try:
                keep = ctxs[0].new_page()  # new_page() = чистая about:blank
            except Exception:  # noqa: BLE001
                keep = None
        for ctx in ctxs:
            for pg in list(ctx.pages):
                if keep is not None and pg == keep:
                    continue
                try:
                    pg.close()
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass


# --- Remote API Dolphin (создание профилей в облаке аккаунта; синхронизируется в десктоп) ---
DOLPHIN_REMOTE = os.environ.get('DOLPHIN_REMOTE_API', 'https://dolphin-anty-api.com').rstrip('/')


# Remote API мимо системного прокси (тот рвёт TLS -> SSL EOF) + релакс-TLS + ретраи.
_REMOTE_OPENER = None


def _dolphin_remote(method, path, body=None, timeout=60, token=None):
    """Запрос к Remote API Dolphin. Токен: явный аргумент (из job) ИЛИ env DOLPHIN_TOKEN.
    Через no-proxy opener (системный прокси рвёт TLS: SSL UNEXPECTED_EOF) + 3 ретрая."""
    global _REMOTE_OPENER
    if _REMOTE_OPENER is None:
        import ssl as _ssl
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE
        _REMOTE_OPENER = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_ctx))
    tok = token or os.environ.get('DOLPHIN_TOKEN', '')
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(DOLPHIN_REMOTE + path, data=data, method=method, headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': 'Bearer ' + tok,
        'Referer': 'https://app.dolphin-anty-ru.online/',
        'User-Agent': 'rusprom-provisioner'})
    last = None
    for _att in range(3):
        try:
            with _REMOTE_OPENER.open(req, timeout=timeout) as r:
                raw = r.read().decode('utf-8', 'replace').strip()
                if not raw:
                    return {'success': True, '_empty': True}  # 204/пустое тело = успех (PATCH)
                return json.loads(raw)
        except urllib.error.HTTPError as he:
            # HTTP-ответ есть (4xx/5xx) — не сетевой сбой, вернуть тело/код как есть
            body = ''
            try:
                body = he.read().decode('utf-8', 'replace')
            except Exception:  # noqa: BLE001
                pass
            try:
                return json.loads(body) if body.strip() else {'error': True, 'http': he.code}
            except Exception:  # noqa: BLE001
                return {'error': True, 'http': he.code, 'body': body[:120]}
        except Exception as e:  # noqa: BLE001 (SSL EOF/таймаут)
            last = e
            time.sleep(1.5 * (_att + 1))
    raise last if last else RuntimeError('dolphin remote fail')


def _socks5_to_dolphin(url):
    """socks5://user:pass@host:port -> {type,host,port,login,password} (формат прокси Dolphin)."""
    m = re.match(r'(socks5|socks4|https?)://(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', url or '')
    if not m:
        return None
    scheme, user, pw, host, port = m.groups()
    p = {'type': 'socks5' if scheme.startswith('socks') else scheme, 'host': host, 'port': int(port)}
    if user:
        p['login'] = user
        p['password'] = pw or ''
    return p


def dolphin_gen_fingerprint(version=130, screen='1920x1080', token=None):
    """Сгенерировать когерентный отпечаток (UA+webgl+os) через Remote API."""
    q = urllib.parse.urlencode({'platform': 'windows', 'browser_type': 'anty',
                                'browser_version': version, 'type': 'fingerprint', 'screen': screen})
    return _dolphin_remote('GET', '/fingerprints/fingerprint?' + q, token=token)


def dolphin_create_profile(name, tags, proxy, version=130, token=None):
    """Создать профиль: генерим отпечаток и собираем payload (canvas/webgl=noise, webrtc=altered,
    tz/locale=auto — берут страну прокси), крепим статичный socks5."""
    fp = dolphin_gen_fingerprint(version, token=token)
    if not (isinstance(fp, dict) and 'userAgent' in fp and 'webgl' in fp and 'os' in fp):
        raise RuntimeError('плохой отпечаток: ' + json.dumps(fp, ensure_ascii=False)[:200])
    os_name = str((fp.get('os') or {}).get('name', 'Windows')).lower()
    plat = 'windows' if 'win' in os_name else ('macos' if 'mac' in os_name else 'linux')
    webgl = fp.get('webgl') or {}
    payload = {
        'name': name, 'tags': tags, 'browserType': 'anty', 'mainWebsite': '', 'platform': plat,
        'useragent': {'mode': 'manual', 'value': fp['userAgent']},
        'webrtc': {'mode': 'altered', 'ipAddress': None},
        'canvas': {'mode': 'noise'}, 'webgl': {'mode': 'noise'},
        'webglInfo': {'mode': 'manual', 'vendor': webgl.get('unmaskedVendor', 'Google Inc.'),
                      'renderer': webgl.get('unmaskedRenderer', 'ANGLE (Intel)'),
                      'webgl2Maximum': fp.get('webgl2Maximum', {})},
        'timezone': {'mode': 'auto', 'value': None}, 'locale': {'mode': 'auto', 'value': None},
        'geolocation': {'mode': 'auto', 'latitude': None, 'longitude': None, 'accuracy': None},
        'cpu': {'mode': 'manual', 'value': 6}, 'memory': {'mode': 'manual', 'value': 8},
        'doNotTrack': False, 'fingerprint': fp, 'proxy': proxy}
    return _dolphin_remote('POST', '/browser_profiles', payload, token=token)


def _host(url):
    m = re.match(r'https?://([^/]+)', url or '')
    return (m.group(1) if m else '').lower().replace('www.', '')


_SOCIAL = ('2gis', 'yandex', 'google', 'vk.com', 'ok.ru', 'wa.me', 't.me', 'telegram',
           'instagram', 'facebook', 'youtube', 'wikipedia', 'gis.ru', 'zoon', 'flamp',
           'avito', 'gosuslugi', 'nalog')
_PHONE_RE = re.compile(r'(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')
_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')


def _extract_contacts(html, text, base_host):
    """Телефон/email/внешний-сайт из отрендеренной карточки (регекс+ссылки, не CSS)."""
    phones = sorted(set(re.sub(r'[\s\-()]', '', p) for p in _PHONE_RE.findall(text or '')))
    emails = sorted(set(e.lower() for e in _EMAIL_RE.findall((text or '') + ' ' + (html or ''))
                        if not e.lower().endswith(('.png', '.jpg', '.svg', '.webp'))))
    sites = []
    for u in re.findall(r'href="(https?://[^"]+)"', html or ''):
        h = _host(u)
        if h and base_host.split(':')[0] not in h and not any(s in h for s in _SOCIAL):
            sites.append(h)
    return {'phones': phones, 'emails': emails, 'ext_sites': sorted(set(sites))[:8]}


def _find_chromium():
    """Найти chrome.exe среди вероятных мест установки (служба LocalSystem не видит
    браузер в профиле Администратора по дефолтному пути — ищем явно и укажем путь)."""
    import glob
    roots = []
    env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
    if env:
        roots.append(env.replace('\\\\', '\\'))
    roots += [r'C:\sender\pw-browsers',
              r'C:\Users\Administrator\AppData\Local\ms-playwright',
              os.path.expanduser(r'~\AppData\Local\ms-playwright'),
              r'C:\Windows\system32\config\systemprofile\AppData\Local\ms-playwright']
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        # рекурсивный поиск — не зависим от точной структуры папок Playwright
        for exe in ('chrome.exe', 'headless_shell.exe'):
            hits = glob.glob(os.path.join(root, '**', exe), recursive=True)
            if hits:
                return sorted(hits)[-1]
    return None


def _mask(s):
    """Замаскировать креды/ключи/IP в строке для безопасного вывода в лог."""
    s = re.sub(r'//([^:@/]+):([^@/]+)@', '//ЛОГИН:ПАРОЛЬ@', s or '')
    s = re.sub(r'(?i)(key|token|pass|password|apikey|api_key)=([^&\s]+)', r'\1=***', s)
    s = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'IP', s)
    return s


def diag_proxy():
    """Разобрать РЕАЛЬНЫЙ формат PROXY_URL/PROXY_URLV2 (владелец просил «провалиться в
    значения»). Креды/ключи/IP маскируем. Если var — http-ссылка с путём/квери (похоже
    на API-ротатор), дёргаем её и показываем, ЧТО она возвращает (тоже маскируя)."""
    rep = {}
    for var in ('PROXY_URL', 'PROXY_URLV2', 'PROXY_URLV3'):
        raw = (os.environ.get(var, '') or '').strip()
        d = {'present': bool(raw), 'len': len(raw)}
        if raw:
            p = urllib.parse.urlsplit(raw if '://' in raw else 'http://' + raw)
            d.update({'scheme': p.scheme or '(нет)', 'host': p.hostname, 'port': p.port,
                      'has_auth': bool(p.username), 'path': p.path or '',
                      'has_query': bool(p.query), 'skeleton': _mask(raw)[:160]})
            # похоже на API-ротатор (http-ссылка с путём/квери) — посмотрим ответ
            if (p.scheme in ('http', 'https')) and (p.path not in ('', '/') or p.query):
                try:
                    body = urllib.request.urlopen(raw, timeout=25).read()[:400]
                    d['fetch_status'] = 'ok'
                    d['fetch_sample'] = _mask(body.decode('utf-8', 'replace'))[:300]
                except Exception as e:  # noqa: BLE001
                    d['fetch_err'] = str(e)[:100]
        rep[var] = d
    rep['runner_python'] = sys.executable  # СЮДА ставить PySocks: "<путь>" -m pip install PySocks
    try:
        import socks  # noqa: F401  PySocks
        rep['pysocks'] = True
    except Exception as e:  # noqa: BLE001
        rep['pysocks'] = False
        rep['pysocks_err'] = str(e)[:80]
    # сверка наличия ВСЕХ ожидаемых ключей (маскированно — только есть/нет + длина)
    keys = {}
    for k in ('DROP_URL', 'DROP_TOKEN', 'JOB_SECRET', 'CAPMONSTER_KEY', 'TWOCAPTCHA_KEY',
              'RUCAPTCHA_KEY', 'XMLRIVER_USER', 'XMLRIVER_KEY', 'DADATA_TOKEN',
              'PROVIDER_API_KEY', 'PROVIDER_BASE_URL', 'VK_TOKEN'):
        v = os.environ.get(k, '') or ''
        keys[k] = f'ЕСТЬ({len(v)})' if v else 'НЕТ'
    rep['keys'] = keys
    # скан ИМЁН переменных (без значений) — поймать опечатки/другие имена в файле
    rep['env_names'] = sorted(k for k in os.environ if any(
        t in k.upper() for t in ('DADA', 'VK', 'CAPTCHA', 'XMLRIVER', 'PROXY', 'DROP', 'PROVIDER')))
    # прочитать сам файл секретов — показать КАК записаны ключи (имена/формат, БЕЗ значений)
    secpath = os.path.join(DIR, 'runner-secrets.env')
    fk = []
    try:
        with open(secpath, encoding='utf-8', errors='replace') as f:
            for ln in f:
                s = ln.rstrip('\n')
                if not s.strip() or s.strip().startswith('#') or '=' not in s:
                    continue
                k, v = s.split('=', 1)
                fk.append({'key': repr(k), 'val_len': len(v),
                           'placeholder<': v.strip().startswith('<'),
                           'has_quotes': v.strip()[:1] in ('"', "'")})
    except Exception as e:  # noqa: BLE001
        fk = [{'read_err': str(e)[:80]}]
    rep['file_keys'] = fk
    return {'proxy_diag': rep}


def handle_captcha(page, url, prox=None):
    """Определить и РЕШИТЬ капчу на УЖЕ открытой странице (переиспользуемо в батч-прогонах:
    одна сессия профиля, много страниц). Возвращает (html, captcha_type_после) — kind=None если
    прошли/капчи не было. reCAPTCHA→CapMonster, Yandex SmartCaptcha→2captcha, Cloudflare→CapMonster."""
    try:
        html = page.content()
    except Exception:  # noqa: BLE001
        return '', None
    kind, sk = _detect(html)
    if not kind:
        return html, None
    # КАСКАД до 3 раундов: human-check (кнопка «Подтвердить» на rate-limit чеко) после клика
    # может раскрыться в SmartCaptcha — она решится следующим раундом. Выход: капчи нет / нет
    # прогресса (kind не сменился за раунд).
    for _r in range(3):
        prev = kind
        try:
            if kind == 'human-check':
                # страница «с вашего IP много запросов, подтвердите что вы человек»
                for sel in ('button:has-text("Подтвердить")', 'text=Подтвердить',
                            'input[type=submit]', 'form button', 'button'):
                    try:
                        page.click(sel, timeout=3000); break
                    except Exception:  # noqa: BLE001
                        continue
                page.wait_for_timeout(3500)
            elif kind == 'recaptcha' and sk:
                token = solve_recaptcha_v2(url, sk)
                if token:
                    page.evaluate("(t)=>{let e=document.getElementById('g-recaptcha-response');"
                                  "if(e){e.value=t;e.style.display='block';}}", token)
                    for sel in ('button:has-text(\"Подтвердить\")', 'input[type=submit]', 'form button'):
                        try:
                            page.click(sel, timeout=3000); break
                        except Exception:  # noqa: BLE001
                            continue
                    page.wait_for_timeout(6000)
            elif kind == 'smartcaptcha':
                for gsel in ('text=Я не робот', 'text=Нажмите, чтобы продолжить',
                             '.CheckboxCaptcha-Button', '[class*=CheckboxCaptcha]', 'input[type=checkbox]'):
                    try:
                        page.click(gsel, timeout=2500); page.wait_for_timeout(2500); break
                    except Exception:  # noqa: BLE001
                        continue
                yk = _ysc_sitekey(page, sk)
                token = solve_yandex_smartcaptcha(url, yk, prox) if yk else None
                if token:
                    page.evaluate("(t)=>{try{if(typeof window.__ysc_cb==='function'){window.__ysc_cb(t);}}"
                                  "catch(e){}try{document.querySelectorAll('input[name=\"smart-token\"]')"
                                  ".forEach(e=>{e.value=t;});}catch(e){}}", token)
                    for sel in ('button[type=submit]', 'input[type=submit]', 'form button'):
                        try:
                            page.click(sel, timeout=3000); break
                        except Exception:  # noqa: BLE001
                            continue
                    page.wait_for_timeout(6000)
            elif kind == 'cloudflare':
                solve_cloudflare_challenge(page)
                page.wait_for_timeout(3000)
            else:
                break
            html = page.content()
            kind, sk = _detect(html)
        except Exception:  # noqa: BLE001
            break
        if not kind or kind == prev:
            break
    return html, kind


def probe(args):
    if args.get('diag_proxy'):
        return diag_proxy()
    if args.get('dolphin') == 'list':
        try:
            profs = dolphin_list(token=args.get('dolphin_token'))
            diag = None
            if not profs:
                # различаем «приложение не запущено» (ECONNREFUSED) и «пустой список»
                try:
                    req = urllib.request.Request(f'{DOLPHIN_BASE}/browser_profiles',
                                                 headers=_dolphin_headers(args.get('dolphin_token')))
                    raw = urllib.request.urlopen(req, timeout=10).read()[:300]
                    diag = {'local_api': 'ответил', 'raw': raw.decode('utf-8', 'replace')}
                except Exception as le:  # noqa: BLE001
                    diag = {'local_api': 'НЕ ответил', 'err': str(le)[:160]}
            return {'dolphin_profiles': profs, 'count': len(profs), 'local_diag': diag,
                    'dolphin_base': DOLPHIN_BASE,
                    'token_present': bool(args.get('dolphin_token') or os.environ.get('DOLPHIN_TOKEN', ''))}
        except Exception as e:  # noqa: BLE001
            return {'dolphin_err': str(e)[:150],
                    'token_present': bool(os.environ.get('DOLPHIN_TOKEN', ''))}
    if args.get('dolphin') == 'setup':
        # массовое создание профилей через Remote API, все на статичном socks5 (PROXY_URL).
        # токен: из аргумента задания (dolphin_token) ИЛИ из env DOLPHIN_TOKEN.
        tok = args.get('dolphin_token') or os.environ.get('DOLPHIN_TOKEN', '')
        if not tok:
            return {'dolphin_setup_err': 'нет токена (dolphin_token в задании или DOLPHIN_TOKEN в env)'}
        prox_url = args.get('proxy_url') or os.environ.get('PROXY_URL', '')
        proxy = _socks5_to_dolphin(prox_url)
        if not proxy:
            return {'dolphin_setup_err': f'не распарсил PROXY_URL ({(prox_url or "")[:24]}…)'}
        n = int(args.get('count', 20))
        start = int(args.get('start', 1))
        ver = int(args.get('chrome_version', 130))
        tag = args.get('tag', 'rusprom')
        created, errs = [], []
        for i in range(start, start + n):
            name = f'rusprom-{i:02d}'
            try:
                r = dolphin_create_profile(name, [tag], proxy, ver, token=tok)
                data = r.get('data') if isinstance(r, dict) else {}
                pid = (r.get('browserProfileId') or (data or {}).get('id')
                       or r.get('id') if isinstance(r, dict) else None)
                created.append({'name': name, 'id': pid})
            except Exception as e:  # noqa: BLE001
                errs.append({'name': name, 'err': str(e)[:150]})
        return {'dolphin_setup': {'created': created, 'errors': errs,
                'count_ok': len(created), 'proxy_host': proxy.get('host'),
                'proxy_type': proxy.get('type')}}
    url = args.get('url')
    if not url:
        inn = args.get('inn', '')
        url = f'https://checko.ru/search?query={inn}'
    wait_ms = int(args.get('wait_ms', 6000))
    out = {'url': url}
    exe = _find_chromium()
    out['chromium_exe'] = exe
    dolphin_pid = args.get('dolphin_profile')
    from playwright.sync_api import sync_playwright  # импорт внутри — не нужен без Playwright
    with sync_playwright() as p:
        if dolphin_pid:
            # Dolphin{anty}: стартуем профиль (внутри свой прокси+антидетект-отпечаток) и
            # подключаемся к его Chromium по CDP — сильно лучше проходит антибот.
            cdp_ep, dport = dolphin_start(dolphin_pid, headless=bool(args.get('headless_dolphin', False)),
                                          token=args.get('dolphin_token'))
            out['dolphin'] = {'profile': str(dolphin_pid), 'port': dport}
            browser = p.chromium.connect_over_cdp(cdp_ep)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            launch_kw = {'headless': not args.get('headful', False),
                         'args': ['--no-sandbox', '--disable-blink-features=AutomationControlled']}
            if exe:
                launch_kw['executable_path'] = exe
            # мобильный прокси: браузер ходит через него (снимает антибот/датацентр-баны).
            prox = _pick_proxy(args, prefer=args.get('proxy_prefer', 'static'))
            out['proxy_used'] = prox.get('var') if prox else False
            if prox:
                pw_proxy = {'server': prox['server']}
                if prox.get('username'):
                    pw_proxy['username'] = prox['username']
                    pw_proxy['password'] = prox['password']
                    if str(prox.get('scheme', '')).startswith('socks'):
                        out['proxy_warn'] = 'socks-auth-не-поддерживается-chromium'
                launch_kw['proxy'] = pw_proxy
            browser = p.chromium.launch(**launch_kw)
            ctx = browser.new_context(user_agent=UA, locale='ru-RU',
                                      viewport={'width': 1366, 'height': 900},
                                      ignore_https_errors=bool(args.get('ignore_https_errors', False)))
        # перехватчик turnstile.render — на случай Cloudflare Challenge (снимет параметры
        # ДО того как challenge-скрипт их использует). Дёшев, вешаем всегда.
        try:
            ctx.add_init_script(_CF_INIT_JS)
            ctx.add_init_script(_YSC_INIT_JS)  # Yandex SmartCaptcha (2captcha)
        except Exception:  # noqa: BLE001
            pass
        page = ctx.new_page()
        status = None
        try:
            resp = page.goto(url, timeout=45000, wait_until='domcontentloaded')
            status = resp.status if resp else None
            page.wait_for_timeout(wait_ms)  # дать JS дорендерить/антиботу отработать
        except Exception as e:  # noqa: BLE001
            out['error'] = f'goto: {str(e)[:80]}'
        html = ''
        try:
            html = page.content()
            out['title'] = page.title()
            text = page.inner_text('body')[:600]
            out['text_snippet'] = re.sub(r'\s+', ' ', text)
        except Exception as e:  # noqa: BLE001
            out.setdefault('error', f'content: {str(e)[:60]}')
            text = ''
        out['http_status'] = status
        kind, sk = _detect(html)
        out['captcha_type'] = kind
        out['sitekey'] = sk
        # решение reCAPTCHA v2 через CapMonster (если просили и она есть)
        if args.get('solve') and kind == 'recaptcha' and sk:
            token = solve_recaptcha_v2(url, sk)
            out['captcha_solved'] = bool(token)
            if token:
                try:
                    page.evaluate(
                        "(t)=>{let e=document.getElementById('g-recaptcha-response');"
                        "if(e){e.value=t;e.style.display='block';}"
                        "if(window.___grecaptcha_cfg){try{Object.entries("
                        "window.___grecaptcha_cfg.clients).forEach(([k,c])=>{});}catch(_){}}}",
                        token)
                    for sel in ('button:has-text("Подтвердить")', 'input[type=submit]',
                                'button[type=submit]', 'form button'):
                        try:
                            page.click(sel, timeout=3000)
                            break
                        except Exception:  # noqa: BLE001
                            continue
                    page.wait_for_timeout(6000)
                    html = page.content()
                    out['title'] = page.title()
                    out['text_snippet'] = re.sub(r'\s+', ' ', page.inner_text('body')[:600])
                    kind, sk = _detect(html)
                    out['captcha_type'] = kind  # None если прошли
                except Exception as e:  # noqa: BLE001
                    out['solve_err'] = str(e)[:80]
        # Yandex SmartCaptcha через 2captcha (нативный токен — то, что CapMonster не умеет)
        if args.get('solve') and kind == 'smartcaptcha':
            # яндекс-антиробот: сперва «Я не робот»/«Нажмите, чтобы продолжить» —
            # только после этого клика рендерится сам виджет SmartCaptcha с sitekey.
            for gsel in ('text=Я не робот', 'text=Нажмите, чтобы продолжить',
                         '.CheckboxCaptcha-Button', '[class*=CheckboxCaptcha]',
                         'input[type=checkbox]'):
                try:
                    page.click(gsel, timeout=2500)
                    page.wait_for_timeout(2500)
                    break
                except Exception:  # noqa: BLE001
                    continue
            yk = _ysc_sitekey(page, sk)
            out['sitekey'] = yk
            token = solve_yandex_smartcaptcha(url, yk, prox) if yk else None
            out['captcha_solved'] = bool(token)
            if token:
                try:
                    page.evaluate(
                        "(t)=>{try{if(typeof window.__ysc_cb==='function'){window.__ysc_cb(t);}}"
                        "catch(e){}try{document.querySelectorAll("
                        "'input[name=\"smart-token\"]').forEach(e=>{e.value=t;});}catch(e){}}",
                        token)
                    for sel in ('button[type=submit]', 'input[type=submit]', 'form button',
                                'button:has-text(\"Отправить\")'):
                        try:
                            page.click(sel, timeout=3000)
                            break
                        except Exception:  # noqa: BLE001
                            continue
                    page.wait_for_timeout(6000)
                    html = page.content()
                    out['title'] = page.title()
                    out['text_snippet'] = re.sub(r'\s+', ' ', page.inner_text('body')[:600])
                    kind, sk = _detect(html)
                    out['captcha_type'] = kind  # None если прошли
                except Exception as e:  # noqa: BLE001
                    out['solve_err'] = str(e)[:80]
        # прохождение Cloudflare Challenge («Один момент») через CapMonster token-mode
        if args.get('solve') and kind == 'cloudflare':
            passed = solve_cloudflare_challenge(page)
            out['cf_solved'] = passed
            if passed:
                try:
                    html = page.content()
                    out['title'] = page.title()
                    out['text_snippet'] = re.sub(r'\s+', ' ', page.inner_text('body')[:600])
                    kind, sk = _detect(html)
                    out['captcha_type'] = kind  # None если прошли
                except Exception as e:  # noqa: BLE001
                    out['cf_err'] = str(e)[:80]
        # клик в карточку организации (карты: результат-список -> карточка с телефоном
        # грузится вторым XHR только после клика). Пробуем список селекторов, ждём XHR.
        # --- fill v2: ввод текста, поиск поля во всех фреймах ---
        # Реестры вроде Сбербанк-АСТ держат поиск во вложенном документе, поэтому
        # page.fill по главному фрейму не находит поле. Перебираем все фреймы и
        # забираем HTML именно того, где ввод прошёл.
        if args.get('fill'):
            reqs = args['fill'] if isinstance(args['fill'], list) else [args['fill']]
            out['fill_used'] = None
            done = False
            for req in reqs:
                if done:
                    break
                sel = (req or {}).get('selector') or ''
                val = str((req or {}).get('value', ''))
                if not sel:
                    continue
                try:
                    frames = list(page.frames)
                except Exception:  # noqa: BLE001
                    frames = []
                for fr in frames:
                    try:
                        fr.wait_for_selector(sel, timeout=5000)
                        fr.fill(sel, '')
                        fr.fill(sel, val)
                        after = (req or {}).get('click_after')
                        if after:
                            fr.click(after, timeout=5000)
                        elif (req or {}).get('enter', True):
                            fr.press(sel, 'Enter')
                        page.wait_for_timeout(int(args.get('card_wait_ms', 7000)))
                        try:
                            html = fr.content()
                        except Exception:  # noqa: BLE001
                            html = page.content()
                        out['fill_used'] = sel
                        out['fill_frame'] = (fr.url or '')[:200]
                        done = True
                        break
                    except Exception as e:  # noqa: BLE001
                        out['fill_err'] = f'{sel}: {str(e)[:90]}'
                        continue
        # --- fill_seq: заполнить несколько полей подряд и отправить ---
        # Нужен там, где кроме строки поиска надо поменять фильтр (например снять
        # умолчание «с 01.01.2024» на Сбербанк-АСТ, чтобы достать архив).
        if args.get('fill_seq'):
            cfg = args['fill_seq'] or {}
            steps = cfg.get('steps') or []
            out['fill_seq_done'] = 0

            def _find_frame(sel):
                try:
                    frames = list(page.frames)
                except Exception:  # noqa: BLE001
                    frames = []
                for fr in frames:
                    try:
                        fr.wait_for_selector(sel, timeout=4000)
                        return fr
                    except Exception:  # noqa: BLE001
                        continue
                return None

            opener = cfg.get('open_first')
            if opener:
                fr = _find_frame(opener)
                if fr is not None:
                    try:
                        fr.click(opener, timeout=4000)
                        page.wait_for_timeout(1500)
                    except Exception as e:  # noqa: BLE001
                        out['fill_seq_err'] = f'open_first: {str(e)[:70]}'

            last_fr, last_sel = None, None
            for st in steps:
                sel = (st or {}).get('selector') or ''
                val = str((st or {}).get('value', ''))
                if not sel:
                    continue
                fr = _find_frame(sel)
                if fr is None:
                    out['fill_seq_err'] = f'{sel}: не найден ни в одном фрейме'
                    continue
                try:
                    fr.fill(sel, '')
                    fr.fill(sel, val)
                    out['fill_seq_done'] += 1
                    last_fr, last_sel = fr, sel
                except Exception as e:  # noqa: BLE001
                    out['fill_seq_err'] = f'{sel}: {str(e)[:70]}'

            submit = cfg.get('submit')
            try:
                if submit:
                    fr = _find_frame(submit) or last_fr
                    if fr is not None:
                        fr.click(submit, timeout=6000)
                elif last_fr is not None and last_sel:
                    last_fr.press(last_sel, 'Enter')
                page.wait_for_timeout(int(args.get('card_wait_ms', 9000)))
                fr = last_fr or page
                try:
                    html = fr.content()
                except Exception:  # noqa: BLE001
                    html = page.content()
                out['fill_frame'] = (getattr(fr, 'url', '') or '')[:200]
            except Exception as e:  # noqa: BLE001
                out['fill_seq_err'] = f'submit: {str(e)[:70]}'
        # --- eval_js: выполнить свой скрипт на странице ---
        # Нужен там, где поле скрыто или форма отправляется своим обработчиком:
        # скрытый #PageSize на Сбербанк-АСТ, select без fill, POST-выдача.
        if args.get('eval_js'):
            cfg = args['eval_js'] or {}
            script = cfg.get('script') or ''
            ret_expr = cfg.get('return') or ''
            vypolnено = 0
            znachenie = None
            oshibki = []
            celi = [page]
            if cfg.get('all_frames'):
                try:
                    celi = celi + [f for f in page.frames if f is not page.main_frame]
                except Exception:  # noqa: BLE001
                    pass
            for tsel in celi:
                if not script:
                    break
                try:
                    tsel.evaluate('() => { %s }' % script)
                    vypolnено += 1
                except Exception as e:  # noqa: BLE001
                    oshibki.append(str(e)[:160])
            if ret_expr:
                try:
                    znachenie = page.evaluate('() => (%s)' % ret_expr)
                except Exception as e:  # noqa: BLE001
                    oshibki.append('return: ' + str(e)[:160])
            pauza = int(cfg.get('after_ms') or 0)
            if pauza:
                try:
                    page.wait_for_timeout(pauza)
                except Exception:  # noqa: BLE001
                    pass
            if cfg.get('then_click'):
                try:
                    page.click(cfg['then_click'], timeout=15000)
                    page.wait_for_timeout(int(cfg.get('after_click_ms') or 2500))
                except Exception as e:  # noqa: BLE001
                    oshibki.append('then_click: ' + str(e)[:160])
            out['eval_js_ok'] = vypolnено > 0
            out['eval_js_frames'] = vypolnено
            # в лог идёт только длина значения: страница может содержать персональные
            # данные, и целиком в результат они попадать не должны
            out['eval_js_value'] = znachenie
            out['eval_js_value_len'] = len(str(znachenie)) if znachenie is not None else 0
            if oshibki:
                out['eval_js_err'] = ' | '.join(oshibki[:3])

        if args.get('click'):
            sels = args['click'] if isinstance(args['click'], list) else [args['click']]
            out['click_used'] = None
            for sel in sels:
                try:
                    page.click(sel, timeout=4000)
                    page.wait_for_timeout(int(args.get('card_wait_ms', 7000)))
                    html = page.content()
                    out['click_used'] = sel
                    break
                except Exception:  # noqa: BLE001
                    continue
        # эвристика: данные компании отрендерились?
        low = (html or '').lower()
        out['data_found'] = bool(kind is None and (
            'выручк' in low or 'огрн' in low or 'уставный капитал' in low
            or 'основной вид деятельности' in low))
        # извлечение контактов и/или сырой HTML (для карт 2ГИС/Яндекс и разведки)
        if args.get('extract') or args.get('return_html'):
            try:
                full_text = page.inner_text('body')
            except Exception:  # noqa: BLE001
                full_text = ''
            if args.get('extract'):
                out['contacts'] = _extract_contacts(html, full_text, _host(url))
            if args.get('return_html'):
                cap = int(args.get('html_cap', 45000))
                out['html'] = (html or '')[:cap]
                out['text'] = re.sub(r'\s+', ' ', full_text)[:8000]
        # скрин на дроп
        if args.get('screenshot', True):
            try:
                png = page.screenshot(full_page=False)
                name = f'browser-shot-{args.get("inn") or "probe"}-{int(time.time())}.png'
                _drop_up(name, png)
                out['screenshot_drop'] = name
            except Exception as e:  # noqa: BLE001
                out['screenshot_err'] = str(e)[:60]
        if dolphin_pid:
            dolphin_close_tabs(browser)  # иначе профиль сохранит вкладки и грузит их при след. старте
        try:
            browser.close()  # для Dolphin рвёт только CDP; сам профиль гасим ниже
        except Exception:  # noqa: BLE001
            pass
        if dolphin_pid:
            dolphin_stop(dolphin_pid, token=args.get('dolphin_token'))  # освободить слот профиля
    return out


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    try:
        json.dump(probe(args), sys.stdout, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        json.dump({'error': f'probe-failed: {str(e)[:120]}',
                   'hint': 'Playwright установлен? pip install playwright && playwright install chromium'},
                  sys.stdout, ensure_ascii=False)
    # Chromium при teardown иногда отдаёт ненулевой код (rc255) хотя данные готовы —
    # печатаем результат и выходим чисто, чтобы раннер не счёл задание упавшим.
    sys.stdout.flush()
    os._exit(0)


if __name__ == '__main__':
    main()
