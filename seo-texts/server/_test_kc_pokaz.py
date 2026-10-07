# -*- coding: utf-8 -*-
import io, json
o = []
for s in io.open(r'C:\sender\server\_test-kc-kontakty.jsonl', encoding='utf-8'):
    з = json.loads(s)
    o.append('%s | %s | checko=%s | сайт=%s | стр %d/%d | ИНН на стр: %s | номеров %d | %s' % (
        з['inn'], з['итог'], json.dumps(з.get('checko'), ensure_ascii=False)[:150], з.get('сайт'),
        sum(1 for x in з.get('страницы', []) if x[1] == 'ok'), len(з.get('страницы', [])), з.get('инн_живой'),
        len(з.get('номера', [])), (з.get('описание') or '')[:100]))
    for н in з.get('номера', [])[:25]:
        o.append('   %s %s | %s | %s | %s | %s' % (н['номер'], н['доб'], н.get('фио', ''), н.get('должность', '')[:40], н.get('класс', ''), н['страницы'][0][-35:]))
    for x in з.get('закупки', []):
        o.append('   ЗАК %s | %s | %s | %s' % (x.get('url', '')[-50:], x.get('инн_на_странице'), [(л.get('person'), л.get('post'), л.get('phone')) for л in x.get('люди', [])][:2], x.get('ошибка')))
print('===ИТОГ===')
print('\n'.join(o)[:5900])
