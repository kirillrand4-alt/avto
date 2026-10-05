# -*- coding: utf-8 -*-
"""Разведка под мейеровскую базу: какие поля есть и где лежат."""
import glob
import json
import os
import sqlite3

o = {}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
for т in ('companies', 'emails', 'phone_contacts', 'site_facts', 'vne_bazy', 'stage_log'):
    try:
        o[т] = {'колонки': [r[1] for r in c.execute('pragma table_info(%s)' % т)],
                'строк': c.execute('select count(*) from %s' % т).fetchone()[0]}
    except Exception as e:  # noqa: BLE001
        o[т] = repr(e)[:80]
o['таблицы'] = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
# что лежит в stage_log по checko (полные ОКВЭД)
try:
    o['stage_checko'] = c.execute(
        "select count(*), max(ts) from stage_log where stage='checko'").fetchone()
    o['stage_checko_пример'] = (c.execute(
        "select detail from stage_log where stage='checko' and detail<>'' limit 1").fetchone()
        or [''])[0][:400]
except Exception as e:  # noqa: BLE001
    o['stage_checko'] = repr(e)[:80]
c.close()

# база обзвона — ищем файл и её колонки
кандидаты = (glob.glob(r'C:\seostat\**\*obzvon*.db', recursive=True)[:5]
             + glob.glob(r'C:\sender\**\*obzvon*.db', recursive=True)[:5])
o['обзвон_файлы'] = кандидаты
for п in кандидаты[:3]:
    try:
        cc = sqlite3.connect('file:%s?mode=ro' % п, uri=True, timeout=30)
        тт = [r[0] for r in cc.execute("select name from sqlite_master where type='table'")]
        o['обзвон:' + os.path.basename(п)] = {
            т: {'колонки': [r[1] for r in cc.execute('pragma table_info(%s)' % т)][:40],
                'строк': cc.execute('select count(*) from %s' % т).fetchone()[0]}
            for т in тт[:6]}
        cc.close()
    except Exception as e:  # noqa: BLE001
        o['обзвон:' + os.path.basename(п)] = repr(e)[:80]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:7000])
