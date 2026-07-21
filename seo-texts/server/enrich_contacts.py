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

# переиспользуем инфраструктуру verify_company (в той же папке)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_company as VC  # _fetch, _detect_block, _provider_call_stdlib, UA

AGGREGATORS = ('list-org', 'rusprofile', 'checko', 'zachestnyibiznes', 'sbis.ru',
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
                 'company', 'zakup', 'снабж', 'закуп', 'requisites', 'rekvizity')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')


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


def crawl_contacts(site, pace=(6.0, 14.0)):
    """Домашняя + страницы контактов -> объединённый текст (кап по объёму)."""
    pages, texts = [], []
    home, method, meta = VC._fetch(site)
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
        if len(picked) >= 3:
            break
    for u in picked:
        time.sleep(_PACE(*pace))
        h, m, mt = VC._fetch(u)
        if h and not mt.get('captcha_type'):
            texts.append(h)
            pages.append(u)
    # склеиваем текст, режем теги, кап
    blob = ' '.join(texts)
    txt = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', blob, flags=re.S | re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    # оставляем окрестности '@' + слов-ролей, чтобы уложиться в лимит
    return txt[:28000], pages, None


def extract_roles(text, company):
    """Провайдер: email С РОЛЯМИ + ЛПР для холодного письма. Фолбэк — regex."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    if key and EMAIL_RE.search(text):
        prompt = (
            'Из текста сайта компании извлеки контакты С РОЛЯМИ. Компания: '
            f'{company.get("name","")}. Верни СТРОГО JSON без markdown: '
            '{"emails":[{"email":"","role":"директор|снабжение/закупки|гл.инженер|'
            'продажи|бухгалтерия|приёмная|общий","person":"ФИО или пусто"}],'
            '"phones":[""],"best_for_outreach":"email ЛПР для холодного письма '
            '(приоритет закупки>гл.инженер>директор>продажи>общий)"}. '
            'Бери только email этой компании (её домен), не сторонние. Текст:\n' + text[:24000])
        out = None
        for _ in range(3):
            try:
                out = VC._provider_call_stdlib(prompt)
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


def enrich_one(company, pace):
    r = {'inn': company.get('inn'), 'name': company.get('name')}
    site = company.get('site')
    src = 'given'
    if not site or not _is_own_site(site if site.startswith('http') else 'http://' + site):
        # list-org и поисковик — каждый по одному потоку (не грузим один хост),
        # но между собой параллельны (разные сайты)
        with _SEM_LISTORG:
            site, src = find_site_via_listorg(company)
            time.sleep(_PACE(1.5, 4.0))
        if not site:
            with _SEM_SEARCH:
                site, src = find_site_via_search(company)
                time.sleep(_PACE(1.5, 4.0))
    if not site:
        r['error'] = f'сайт не найден ({src})'
        r['method'] = src
        return r
    if not site.startswith('http'):
        site = 'http://' + site
    r['site'] = _domain(site)
    r['site_source'] = src
    time.sleep(_PACE(*pace))
    text, pages, err = crawl_contacts(site, pace)
    if err:
        r['error'] = err
        return r
    data, how = extract_roles(text, company)
    emails = data.get('emails', [])
    for e in emails:
        e['mx_ok'] = mx_ok(e.get('email', ''))
    r.update({'emails': emails, 'phones': data.get('phones', []),
              'best_for_outreach': data.get('best_for_outreach', ''),
              'pages_crawled': pages, 'extract': how, 'method': 'ok'})
    if not emails:
        r['error'] = 'email на сайте не найдены'
    return r


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    companies = args.get('companies', [])
    pace = (float(args.get('pace_min', 6.0)), float(args.get('pace_max', 14.0)))
    workers = max(1, min(int(args.get('workers', 6)), 12))

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
    from collections import Counter
    with_email = sum(1 for r in results if r.get('emails'))
    with_lpr = sum(1 for r in results if r.get('best_for_outreach'))
    site_src = Counter(r.get('site_source') for r in results if r.get('site_source'))
    json.dump({'results': results, 'count': len(results),
               'summary': {'with_email': with_email, 'with_lpr_email': with_lpr,
                           'site_sources': dict(site_src)}},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
