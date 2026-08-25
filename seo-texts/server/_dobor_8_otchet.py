# -*- coding: utf-8 -*-
"""Свод по добору: что реально легло в базу (по метке), примеры, откат."""
import json
import os
import sqlite3

RO = 'file:C:/sender/enrich.db?mode=ro'
ZH = r'C:\sender\_tmp\kesh-dobor.jsonl'

n = p = t = ob = prop = sboev = 0
with open(ZH, encoding='utf-8') as f:
    for s in f:
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        if d.get('сбой'):
            sboev += 1
            continue
        if d.get('пропуск'):
            prop += 1
            continue
        p += d.get('p', 0)
        t += d.get('t', 0)
        ob += d.get('obsh', 0)
print('ЖУРНАЛ: строк %d | компаний записано %d | сбоев (будут добраны при возобновлении) %d '
      '| пропусков %d' % (n, n - sboev - prop, sboev, prop))
print('  почт %d, телефонов %d, из них общих %d' % (p, t, ob))

c = sqlite3.connect(RO, uri=True, timeout=60)
q = {
 'почт с меткой кэш-добор': "select count(*) from emails where coalesce(pometka,'') like '%кэш-добор%'",
 '  из них source=кэш-добор': "select count(*) from emails where source='кэш-добор'",
 "  из них source=own-site (add_email переписал)":
     "select count(*) from emails where source='own-site' and coalesce(pometka,'') like '%кэш-добор%'",
 'компаний с новой почтой': "select count(distinct inn) from emails where coalesce(pometka,'') like '%кэш-добор%'",
 'телефонов с меткой кэш-добор': "select count(*) from phone_contacts where source like 'кэш-добор%'",
 '  помечено общими': "select count(*) from phone_contacts where source like 'кэш-добор; общий%'",
 '  с ролью общий': "select count(*) from phone_contacts where source like 'кэш-добор%' and role='общий'",
 'компаний с новым телефоном': "select count(distinct inn) from phone_contacts where source like 'кэш-добор%'",
 'best_email проставлен у затронутых (должно быть 0 от нас)':
     "select count(*) from companies where coalesce(best_email,'')<>'' and inn in "
     "(select inn from emails where coalesce(pometka,'') like '%кэш-добор%')",
 'людей записано (не пишем)': "select count(*) from people where source like 'кэш-добор%'",
}
for k, s in q.items():
    print('%s: %s' % (k, c.execute(s).fetchone()[0]))

print('роли новых почт:', json.dumps(
    [list(r) for r in c.execute(
        "select coalesce(role,'(пусто)'), count(*) n from emails "
        "where coalesce(pometka,'') like '%кэш-добор%' group by 1 order by n desc limit 8")],
    ensure_ascii=False))
print('10 ПРИМЕРОВ почт:', json.dumps(
    [list(r) for r in c.execute(
        "select inn, email, coalesce(role,''), coalesce(source,''), "
        "substr(coalesce(source_url,''),1,44) from emails "
        "where coalesce(pometka,'') like '%кэш-добор%' limit 10")], ensure_ascii=False))
print('10 ПРИМЕРОВ телефонов:', json.dumps(
    [list(r) for r in c.execute(
        "select inn, phone, coalesce(role,''), substr(source,1,46) from phone_contacts "
        "where source like 'кэш-добор%' limit 10")], ensure_ascii=False))
print('размер журнала:', os.path.getsize(ZH), 'байт')
c.close()
