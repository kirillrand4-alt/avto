# -*- coding: utf-8 -*-
"""7 744 факта (60,4 %) держатся ТОЛЬКО на странице поиска. Прежде чем звать это бедой,
делю поиск надвое — иначе я обвиню годное вместе с негодным.

    ПОИСК ПО НОМЕРУ ЗАКУПКИ (`searchString=31705178869`) — это адресный запрос: выдача
    вернёт ровно ту закупку. По силе почти карточка.
    ПОИСК ПО СЛОВУ (`searchString=компрессор`) — это широкий запрос: страница докажет, что
    слово есть в выдаче, но НЕ докажет, что машина у этого предприятия.

Считаю обе доли и печатаю по три примера каждой. Ноль в любой группе будет означать состояние
парка, а не мою слепоту: обе ветки разбираются одним и тем же разбором адреса.
"""
import collections, io, json, os, re, urllib.parse, urllib.request
OPS = r'C:\sender\_ops'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
POISK = re.compile(r'(zakupki\.gov\.ru/epz/order/extendedsearch|procedures/?\?search=|'
                   r'/poisk/search|\?query_field=|procedures\?name=)')


def zapros(u):
    """Что именно спрошено у поиска."""
    q = urllib.parse.urlsplit(u).query
    p = urllib.parse.parse_qs(q)
    for k in ('searchString', 'search', 'query_field', 'name', 'keywords', 'q'):
        if p.get(k):
            return urllib.parse.unquote(p[k][0])
    return ''


def stroki(imya):
    put = os.path.join(OPS, imya)
    if os.path.exists(put):
        return io.open(put, encoding='utf-8', errors='replace').read().splitlines()
    try:
        return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                       timeout=300).read().decode('utf-8', 'replace').splitlines()
    except Exception:  # noqa: BLE001
        return []


sch = collections.Counter()
prim = collections.defaultdict(list)
for f in ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl', 'PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl',
          'PARK-RTS-PODTV-3S.jsonl']:
    for s in stroki(f):
        try: z = json.loads(s)
        except Exception: continue
        us = [u for u in str(z.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if not us or any(not POISK.search(u) for u in us):
            continue          # у факта есть хоть одна НЕ-поисковая ссылка — он не в счёт
        vidy = set()
        for u in us:
            t = zapros(u)
            cifr = len(re.sub(r'\D', '', t))
            # ПОПРАВКА, КУПЛЕННАЯ ПРИМЕРАМИ. Первый разбор звал «широким запросом» всё,
            # где есть буквы, и насчитал 4 351 «слабый» факт. Глаза показали, что это:
            #     etpgpb.ru/procedures/?search=ГП415801   ->  ГП415801
            #     etpgpb.ru/procedures/?search=АП029772   ->  АП029772
            # то есть КОД ПРОЦЕДУРЫ с буквенной приставкой — такой же адресный запрос, как
            # номер закупки, и выдача по нему вернёт ровно одну процедуру. Широкий запрос —
            # это «компрессор», а не «ГП415801». Различаю по наличию ПРОБЕЛА и по доле цифр.
            slov = len(t.split())
            if t and cifr >= 5 and slov == 1:
                vidy.add('адресный запрос (номер закупки или код процедуры)')
            elif t:
                vidy.add('по СЛОВУ (широкий запрос)')
            else:
                vidy.add('запрос из адреса не читается')
            if len(prim[list(vidy)[-1] if vidy else '']) < 3:
                pass
        klyuch = ('адресный запрос (номер закупки или код процедуры)'
                  if vidy == {'адресный запрос (номер закупки или код процедуры)'} else
                  'по СЛОВУ (широкий запрос)' if vidy == {'по СЛОВУ (широкий запрос)'} else
                  'смешанные / нечитаемые')
        sch[klyuch] += 1
        if len(prim[klyuch]) < 3:
            prim[klyuch].append('%s   ->   %s' % (us[0][:96], zapros(us[0])[:40]))
print('########## ФАКТЫ, У КОТОРЫХ ВСЕ ССЫЛКИ — ПОИСКОВЫЕ')
vsego = sum(sch.values())
for k, v in sch.most_common():
    print('  %-42s %6d  (%.1f%%)' % (k, v, 100.0 * v / max(1, vsego)))
print('  ВСЕГО таких фактов %d' % vsego)
for k in sch:
    print('  --- примеры: %s' % k)
    for p in prim[k]:
        print('     %s' % p)
print('ИТОГ ' + json.dumps({k: v for k, v in sch.items()}, ensure_ascii=False))
