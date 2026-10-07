# -*- coding: utf-8 -*-
import io, json, os, re, sys, time
sys.path.insert(0, r'C:\sender\server')
import kc_kontakty as KK
import cc_checko_proxy as CP
KK.ВЫХОД = r'C:\sender\server\_test-kc-kontakty.jsonl'
if os.path.exists(KK.ВЫХОД):
    os.remove(KK.ВЫХОД)
б = json.load(io.open(r'C:\sender\server\kc-pishch-otbor.json', encoding='utf-8'))
KK.ПРОКСИ.extend(п for п in (CP.Прокси(x) for x in json.load(open(r'C:\sender\server\checko-proxies.json'))) if п.get('https://checko.ru/')[0] == 200)
t0 = time.time()
for инн in ('7724766868', '1660297582'):
    к = dict(б[инн]); к['сайт'] = (re.split(r'[\s,;|]+', к['сайт'].strip()) or [''])[0]
    KK.одна(к)
o = []
for s in io.open(KK.ВЫХОД, encoding='utf-8'):
    з = json.loads(s)
    o.append({'inn': з['inn'], 'итог': з['итог'], 'checko': з.get('checko'), 'сайт': з.get('сайт'), 'страниц': len(з.get('страницы', [])),
              'ок_страниц': sum(1 for x in з.get('страницы', []) if x[1] == 'ok'), 'инн_живой': з.get('инн_живой'),
              'номера': [(н['номер'], н['доб'], н.get('фио', ''), н.get('должность', ''), н.get('класс', '')) for н in з.get('номера', [])][:12],
              'описание': з.get('описание'), 'закупки': [(x.get('url', '')[-40:], x.get('инн_на_странице'), [(л.get('person'), л.get('post'), л.get('phone')) for л in x.get('люди', [])][:2], x.get('ошибка')) for x in з.get('закупки', [])][:5]})
print('===ИТОГ===')
print(json.dumps({'сек': round(time.time() - t0), 'o': o}, ensure_ascii=False, indent=0)[:5800])
