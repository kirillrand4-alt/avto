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
import urllib.request

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
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context(user_agent=UA, locale='ru-RU',
                                  viewport={'width': 1366, 'height': 900})
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
                out['html'] = (html or '')[:45000]
                out['text'] = re.sub(r'\s+', ' ', full_text)[:6000]
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
