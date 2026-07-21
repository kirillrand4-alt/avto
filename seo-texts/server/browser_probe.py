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
    """PROXY_URL (http://user:pass@host:port) -> dict для Playwright и 2captcha | None."""
    if not url:
        return None
    try:
        p = urllib.parse.urlsplit(url if '://' in url else 'http://' + url)
        if not p.hostname:
            return None
        sch = p.scheme or 'http'
        return {'scheme': sch, 'host': p.hostname, 'port': p.port or (443 if sch == 'https' else 80),
                'username': p.username, 'password': p.password or '',
                'server': f'{sch}://{p.hostname}:{p.port or 80}'}
    except Exception:  # noqa: BLE001
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


def solve_yandex_smartcaptcha(url, sitekey):
    """Решить Yandex SmartCaptcha через 2captcha -> smart-token | None.
    Если задан PROXY_URL — решаем ЧЕРЕЗ наш прокси (YandexSmartCaptchaTask), чтобы токен
    был валиден для НАШЕГО IP (у яндекс-антиробота токен привязан к IP). Без прокси —
    Proxyless (пул 2captcha)."""
    key = _twocap_key()
    if not key or not sitekey:
        return None
    prox = _parse_proxy(os.environ.get('PROXY_URL', ''))
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


def probe(args):
    url = args.get('url')
    if not url:
        inn = args.get('inn', '')
        url = f'https://checko.ru/search?query={inn}'
    wait_ms = int(args.get('wait_ms', 6000))
    out = {'url': url}
    exe = _find_chromium()
    out['chromium_exe'] = exe
    from playwright.sync_api import sync_playwright  # импорт внутри — не нужен без Playwright
    with sync_playwright() as p:
        launch_kw = {'headless': not args.get('headful', False),
                     'args': ['--no-sandbox', '--disable-blink-features=AutomationControlled']}
        if exe:
            launch_kw['executable_path'] = exe
        # мобильный прокси: браузер ходит через него (снимает антибот на яндексе/картах
        # и датацентр-баны). Отключаемо через {"proxy":false}. Формат PROXY_URL см. выше.
        prox = _parse_proxy(os.environ.get('PROXY_URL', '')) if args.get('proxy', True) else None
        out['proxy_used'] = bool(prox)
        if prox:
            pw_proxy = {'server': prox['server']}
            if prox.get('username'):
                pw_proxy['username'] = prox['username']
                pw_proxy['password'] = prox['password']
            launch_kw['proxy'] = pw_proxy
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(user_agent=UA, locale='ru-RU',
                                  viewport={'width': 1366, 'height': 900})
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
            token = solve_yandex_smartcaptcha(url, yk) if yk else None
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
        browser.close()
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
