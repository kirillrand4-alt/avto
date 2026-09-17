# -*- coding: utf-8 -*-
"""На каком тексте вынесен вердикт «не капекс»: длина перекачанной страницы."""
import io, json

строки = []
with io.open(r'C:\sender\server\dobor_teksta.jsonl', encoding='utf-8', errors='replace') as f:
    for s in f:
        try: з = json.loads(s)
        except Exception: continue
        if з.get('is_capex') is False:
            строки.append({'компания': з.get('компания'),
                           'знаков_в_новой_странице': з.get('знаков'),
                           'было_what': (з.get('было_what') or '')[:80],
                           'стало_what': (з.get('стало_what') or '')[:60],
                           'ссылка': (з.get('url') or '')[:60]})
коротких = sum(1 for x in строки if (x['знаков_в_новой_странице'] or 0) < 2000)
print('===ИТОГ===')
print(json.dumps({'всего_не_капекс': len(строки),
                  'из_них_страница_короче_2000_знаков': коротких,
                  'длины': sorted(x['знаков_в_новой_странице'] or 0 for x in строки),
                  'строки': строки[:8]}, ensure_ascii=False, indent=1)[:3500])
