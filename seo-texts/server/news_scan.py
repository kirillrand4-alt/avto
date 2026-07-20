# -*- coding: utf-8 -*-
"""news_scan: триггерные лиды из новостей. Запрос-триггеры × отрасль × регион →
Google News RSS (реальные ссылки-источники) → провайдер извлекает КАПЕКС-событие →
DaData (имя→ИНН→ОКВЭД-фильтр производства) → события с source_url для верификации.
Гиперлокал (райгазеты/ВК/ОК) добавляется списком source-URL позже (браузер). LLM — провайдер.

stdin: {"queries":[...] или "industries"+"regions", "days":90, "max_items":8, "dadata_token":""}
stdout: {"events":[{company,inn,okved,event_type,what,region,sum,hotness,source_url,
                    source_name,published,is_capex,icp_fit}], "summary":{...}}"""
import os, sys, json, re, time
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_company as VC  # _provider_call_stdlib

TRIGGERS = ['строительство завода', 'запуск цеха', 'новый цех', 'модернизация производства',
            'расширение производства', 'ввод мощностей', 'запуск линии', 'инвестиции в производство',
            'займ ФРП', 'резидент индустриального парка', 'новое производство']
# ОКВЭД-разделы, кому нужны компрессоры/генераторы (производство/энергетика/добыча)
ICP_OKVED = tuple(f'{n:02d}' for n in list(range(10, 34)) + [35, 36, 37, 8, 7, 5, 6])
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'


def rss(query):
    url = ('https://news.google.com/rss/search?q=' + urllib.parse.quote(query)
           + '&hl=ru&gl=RU&ceid=RU:ru')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        body = urllib.request.urlopen(req, timeout=25).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in re.findall(r'<item>(.*?)</item>', body, re.S):
        def g(tag):
            m = re.search(rf'<{tag}>(.*?)</{tag}>', it, re.S)
            return re.sub(r'<!\[CDATA\[|\]\]>', '', m.group(1)).strip() if m else ''
        out.append({'title': g('title'), 'link': g('link'),
                    'pubDate': g('pubDate'), 'source': g('source')})
    return out


def fresh(pubdate, days):
    try:
        dt = parsedate_to_datetime(pubdate)
        return (time.time() - dt.timestamp()) <= days * 86400
    except Exception:  # noqa: BLE001
        return True


def extract_event(title, source):
    prompt = (
        'Из заголовка новости определи, есть ли КАПЕКС-событие компании (стройка/'
        'модернизация/запуск цеха-линии/расширение/инвестиции/займ ФРП), которой скоро '
        'нужно промышленное оборудование. Верни СТРОГО JSON без markdown: '
        '{"is_capex":true/false,"company":"название компании из новости или пусто",'
        '"event_type":"новый завод|модернизация|запуск линии|расширение|инвестиции|найм|прочее",'
        '"what":"что строят/делают кратко","region":"регион/город или пусто",'
        '"sum":"сумма инвестиций если есть","hotness":1-5}. '
        f'Заголовок: "{title}" (источник: {source}).')
    try:
        out = VC._provider_call_stdlib(prompt)
        m = re.search(r'\{.*\}', out or '', re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None


def dadata_suggest(name, token):
    if not name or not token:
        return None
    try:
        body = json.dumps({'query': name, 'count': 1}).encode()
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
            data=body, method='POST', headers={'Content-Type': 'application/json',
            'Accept': 'application/json', 'Authorization': f'Token {token}'})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        s = (d.get('suggestions') or [])
        if not s:
            return None
        data = s[0].get('data', {})
        okved = data.get('okved') or ''
        return {'inn': data.get('inn'), 'okved': okved,
                'name': s[0].get('value'),
                'region': ((data.get('address') or {}).get('data') or {}).get('region'),
                'status': (data.get('state') or {}).get('status')}
    except Exception:  # noqa: BLE001
        return None


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    days = int(args.get('days', 90))
    max_items = int(args.get('max_items', 8))
    token = args.get('dadata_token') or os.environ.get('DADATA_TOKEN', '')
    queries = args.get('queries')
    if not queries:
        inds = args.get('industries', ['металлообработка', 'пищевое производство'])
        regs = args.get('regions', ['Новосибирск', 'Алтайский край', 'Москва'])
        queries = [f'{t} {ind} {reg}' for t in TRIGGERS[:6] for ind in inds for reg in regs]

    # 1) сбор RSS (реальные ссылки-источники)
    raw, seen = [], set()
    for q in queries:
        for it in rss(q):
            key = it['title'][:60]
            if key in seen or not it['title'] or not fresh(it['pubDate'], days):
                continue
            seen.add(key)
            it['query'] = q
            raw.append(it)
    raw = raw[: max_items * len(queries)]

    # 2) извлечение события (провайдер, параллельно)
    def enrich(it):
        ev = extract_event(it['title'], it.get('source', ''))
        if not ev or not ev.get('is_capex'):
            return None
        rec = {'title': it['title'], 'source_url': it['link'],  # ССЫЛКА — обязательна
               'source_name': it.get('source', ''), 'published': it.get('pubDate', ''),
               'event_type': ev.get('event_type'), 'what': ev.get('what'),
               'region': ev.get('region'), 'sum': ev.get('sum'),
               'hotness': ev.get('hotness'), 'company': ev.get('company'), 'is_capex': True}
        # 3) DaData: имя → ИНН + ОКВЭД-фильтр производства
        dd = dadata_suggest(ev.get('company'), token)
        if dd:
            rec.update({'inn': dd['inn'], 'okved': dd['okved'],
                        'company_full': dd['name'], 'status': dd['status']})
            rec['icp_fit'] = str(dd['okved']).replace('.', '')[:2] in ICP_OKVED
        else:
            rec['icp_fit'] = None
        return rec

    with ThreadPoolExecutor(max_workers=8) as ex:
        events = [e for e in ex.map(enrich, raw) if e]
    events.sort(key=lambda e: (e.get('icp_fit') is True, e.get('hotness') or 0), reverse=True)

    from collections import Counter
    json.dump({'events': events, 'count': len(events),
               'summary': {'queries': len(queries), 'raw_items': len(raw),
                           'capex_events': len(events),
                           'icp_fit': sum(1 for e in events if e.get('icp_fit')),
                           'with_inn': sum(1 for e in events if e.get('inn')),
                           'by_type': dict(Counter(e['event_type'] for e in events))}},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
