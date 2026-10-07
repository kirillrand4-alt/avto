# -*- coding: utf-8 -*-
import collections, csv, io, json, re, sqlite3, urllib.parse
ДРОП = r'C:\seostat\drop\drop-storage'
r = list(csv.DictReader(io.open(ДРОП + r'\park-meyer-kandidaty.csv', encoding='utf-8-sig'), delimiter=';'))
ч = [x for x in r if x['Сегмент по осн. ОКВЭД'] and not x['Где у нас'].startswith('в наших') and not x['Запрет панели']
     and (x['Статус ЕГРЮЛ'] or '').upper() not in ('LIQUIDATED', 'LIQUIDATING', 'BANKRUPT') and 'ликвид' not in (x['Статус ЕГРЮЛ'] or '').lower()]
инн = {x['ИНН'] for x in ч}
c = sqlite3.connect('file:%s\\park_panel.db?mode=ro' % ДРОП, uri=True)
кол = [x[1] for x in c.execute('pragma table_info(kontakt)')]
rows = [dict(zip(кол, x)) for x in c.execute('select * from kontakt') if str(x[0]) in инн]
o = {'кандидатов': len(инн), 'контактов': len(rows), 'vid': collections.Counter(x['vid'] for x in rows).most_common(),
     'с_ссылкой': sum(1 for x in rows if x['ssylka']),
     'домены_ссылок': collections.Counter(urllib.parse.urlsplit(x['ssylka'] or '').hostname for x in rows if x['ssylka']).most_common(15),
     'rol': collections.Counter(x['rol'] for x in rows).most_common(12), 'krug': collections.Counter(x['krug'] for x in rows).most_common(),
     'пример': [{k: str(v)[:70] for k, v in x.items()} for x in rows[:5]]}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
