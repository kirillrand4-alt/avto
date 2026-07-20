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
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

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


def probe(args):
    url = args.get('url')
    if not url:
        inn = args.get('inn', '')
        url = f'https://checko.ru/search?query={inn}'
    wait_ms = int(args.get('wait_ms', 6000))
    out = {'url': url}
    from playwright.sync_api import sync_playwright  # импорт внутри — не нужен без Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.get('headful', False),
                                    args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
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
        # эвристика: данные компании отрендерились?
        low = (html or '').lower()
        out['data_found'] = bool(kind is None and (
            'выручк' in low or 'огрн' in low or 'уставный капитал' in low
            or 'основной вид деятельности' in low))
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


if __name__ == '__main__':
    main()
