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
import urllib.request
import urllib.error
import urllib.parse

CAPMONSTER_KEY = os.environ.get('CAPMONSTER_KEY', '')
CAP_BASE = 'https://api.capmonster.cloud'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

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


def extract_via_provider(html, company):
    if GP is None:
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
            msg = GP._raw_stream([{'role': 'user', 'content': prompt}],
                                 'claude-fable-5', 800, thinking=False)
            out = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
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


def _is_challenge(status, body):
    b = (body or '').lower()
    return (status in (403, 503) or 'just a moment' in b
            or 'cf-challenge' in b or 'cf_chl' in b or 'challenge-platform' in b)


def _sitekey(body):
    m = re.search(r'data-sitekey="([^"]+)"', body or '')
    return m.group(1) if m else None


def _fetch(url):
    """GET с браузерными заголовками; при челлендже — CapMonster Turnstile.
    Возвращает (html, method). method: 'direct' | 'capmonster' | 'challenge-unsolved'."""
    headers = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
               'Accept': 'text/html,application/xhtml+xml'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode('utf-8', 'replace')
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        status = e.code
    except Exception as e:  # noqa: BLE001
        return None, f'error:{str(e)[:60]}'

    if not _is_challenge(status, body):
        return body, 'direct'

    # челлендж -> пробуем решить
    token, ua = solve_turnstile(url, _sitekey(body))
    if not token:
        return body, 'challenge-unsolved'
    # повтор с решённым токеном и его user-agent. Полный обмен токена на куку
    # cf_clearance site-specific — при недоборе доводится на боевом сервере.
    try:
        h2 = dict(headers)
        h2['User-Agent'] = ua or UA
        h2['cf-turnstile-response'] = token
        with urllib.request.urlopen(urllib.request.Request(url, headers=h2), timeout=45) as r:
            body2 = r.read().decode('utf-8', 'replace')
        return (body2, 'capmonster') if not _is_challenge(200, body2) else (body2, 'challenge-unsolved')
    except Exception as e:  # noqa: BLE001
        return body, f'capmonster-retry-failed:{str(e)[:40]}'


def verify_one(company, source):
    q = company.get('inn') or f"{company.get('name','')} {company.get('city','')}".strip()
    url = SOURCES.get(source, SOURCES['checko']).format(q=urllib.parse.quote(q))
    html, method = _fetch(url)
    base = {'name': company.get('name'), 'inn_query': company.get('inn'),
            'source_url': url, 'method': method}
    if not html or method in ('challenge-unsolved',) or method.startswith('error'):
        base['error'] = f'fetch не удался ({method})'
        return base
    data = extract_via_provider(html, company) or {}
    base.update({k: data.get(k) for k in
                 ('inn', 'full_name', 'address', 'region', 'revenue',
                  'revenue_year', 'status', 'okved')})
    if not any(base.get(k) for k in ('address', 'revenue', 'full_name')):
        base['error'] = 'реквизиты не извлечены (проверить селекторы/провайдер)'
    return base


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    companies = args.get('companies', [])
    source = args.get('source', 'checko')
    results = []
    for c in companies:
        try:
            results.append(verify_one(c, source))
        except Exception as e:  # noqa: BLE001
            results.append({'name': c.get('name'), 'error': f'exc:{str(e)[:80]}'})
        time.sleep(1.0)  # вежливость к источнику
    json.dump({'results': results, 'count': len(results),
               'capmonster': bool(CAPMONSTER_KEY), 'provider': GP is not None},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
