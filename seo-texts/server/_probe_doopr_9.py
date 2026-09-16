# -*- coding: utf-8 -*-
"""Проба 9: путь 2 (ЕГРЗ) через общую точку `poisk_v_egrz` на ЖИВОЙ ленте соседского
коллектора `collector_egrz.col_egrz`. Источник бесплатный (открытый OData ЕГРЗ),
провайдер и xmlriver не трогаются, в базы ничего не пишется.

Меряем: сколько безымянных событий доопределяется ТОЛЬКО путём 2 и сколько
записей ЕГРЗ вообще нашлось под наши объекты. Итог печатается ПОСЛЕДНИМ.
"""
import json
import sys
import time

sys.path.insert(0, r'C:\sender\_tmp')
sys.path.insert(0, r'C:\sender\server')
import doopredelenie as DP  # noqa: E402

JS = r'C:\sender\server\news_stream.jsonl'
recs = []
for line in open(JS, encoding='utf-8', errors='replace'):
    line = line.strip()
    if line:
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
anon = [r for r in recs if not (r.get('company') or '').strip()]
# берём безымянные ПРО СТРОЙКУ и с регионом — только там ЕГРЗ вообще применим
kand = [r for r in anon if (r.get('region') or '').strip()
        and any(w in ((r.get('title') or '') + (r.get('what') or '')).lower()
                for w in ('строит', 'построя', 'возвед', 'заложил', 'проект'))][:60]

t0 = time.time()
ctx = DP.Kontekst(internet=True, razresheno_platit=False, puti=['егрз'],
                  egrz_lenta=True, feed_dney=180, feed_max=400,
                  dadata=lambda imya: None, log=lambda s: print('LOG', s))
nashli, primery, prichiny = 0, [], {}
for r in kand:
    res = DP.doopredelit({'title': r.get('title'), 'what': r.get('what'),
                          'region': r.get('region'), 'source_url': r.get('source_url'),
                          'published': r.get('published')}, ctx)
    if res.get('company'):
        nashli += 1
        if len(primery) < 8:
            primery.append(((r.get('title') or '')[:60], res['company'], res['uverennost'],
                            res['uliki'][0][:80]))
    else:
        for u in res['uliki']:
            k = u.split(':')[0]
            prichiny[k] = prichiny.get(k, 0) + 1

lenta = DP._FEED_KESH.get(('egrz', 180, 400)) or []
print()
print('==================== ИТОГ (главное) ====================')
print('лента ЕГРЗ за 180 дней: %d заключений, снята за %.0f с' % (len(lenta), time.time() - t0))
if lenta:
    print('пример записи ЕГРЗ: %s | %s | %s' % ((lenta[0].get('company_name') or '')[:40],
                                                (lenta[0].get('region') or '')[:25],
                                                (lenta[0].get('what') or '')[:70]))
print('кандидатов (безымянные про стройку, с регионом): %d из %d безымянных'
      % (len(kand), len(anon)))
print('путь 2 дал имя: %d (%.0f%% от кандидатов)' % (nashli, 100.0 * nashli / max(1, len(kand))))
print('почему не вышло:', prichiny)
for p in primery:
    print('  %s -> %s [%s] %s' % p)
