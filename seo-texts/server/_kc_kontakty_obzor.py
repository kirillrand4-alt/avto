# -*- coding: utf-8 -*-
import io, json
o = []
for s in io.open(r'C:\sender\server\kc-kontakty.jsonl', encoding='utf-8', errors='replace'):
    з = json.loads(s)
    зак = з.get('закупки', [])
    o.append('%s | %s | checko=%s | сайт=%s | стр %d/%d | инн_стр=%s | ном %d (подп %d) | зак: карт %d, с ИНН %d, людей %d, ош %s' % (
        з['inn'], з['итог'][:20], (з.get('checko') or {}).get('checko'), (з.get('сайт') or '')[:30],
        sum(1 for x in з.get('страницы', []) if x[1] == 'ok'), len(з.get('страницы', [])), з['inn'] in (з.get('инн_живой') or []),
        len(з.get('номера', [])), sum(1 for н in з.get('номера', []) if н.get('класс')),
        sum(1 for x in зак if x.get('url')), sum(1 for x in зак if x.get('инн_на_странице')), sum(len(x.get('люди') or []) for x in зак),
        [x.get('ошибка')[:40] for x in зак if x.get('ошибка')][:2]))
print('===ИТОГ===')
print('\n'.join(o)[-5800:])
