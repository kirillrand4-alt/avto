# -*- coding: utf-8 -*-
"""Сколько ждёт в очереди Зенки и сколько паспортов из-за неё стоит."""
import io, json, os, sqlite3, time
ZEN = r'C:\seostat\drop\zenno'
o = {}
п = os.path.join(ZEN, 'ochered.txt')
if os.path.exists(п):
    with io.open(п, encoding='utf-8', errors='replace') as f:
        строки = [s.strip() for s in f if s.strip()]
    o['очередь'] = {'строк': len(строки), 'примеры': строки[:3]}
d = os.path.join(ZEN, 'dispetcher.json')
if os.path.exists(d):
    try:
        дд = json.load(io.open(d, encoding='utf-8', errors='replace'))
        шаб = дд.get('shablony') or дд.get('шаблоны') or []
        o['диспетчер'] = {'ключи': sorted(дд.keys())[:8], 'шаблонов': len(шаб),
                          'с_потоками': [x for x in шаб
                                         if (x.get('potokov_seychas') or 0) > 0][:5],
                          'сумма_потоков': sum((x.get('potokov_seychas') or 0) for x in шаб)}
    except Exception as e:
        o['диспетчер'] = 'не разобрался: %r' % (e,)
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o['паспортов_ждут_кэша'] = c.execute(
    "select count(*) from site_facts where format=0 and note like '%кэш%'").fetchone()[0]
o['паспортов_не_готово_всего'] = c.execute(
    'select count(*) from site_facts where format=0').fetchone()[0]
o['компаний_с_сайтом_без_паспорта'] = c.execute(
    "select count(*) from companies c where coalesce(c.site,'')<>'' "
    'and not exists(select 1 from site_facts f where f.inn=c.inn)').fetchone()[0]
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:2500])
