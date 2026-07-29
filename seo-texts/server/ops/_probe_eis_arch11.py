# -*- coding: utf-8 -*-
"""Размер базы и остаток — чтобы честно посчитать, окупается ли полный проход."""
import json
import sys
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

db = EDB.EnrichDB()
e = db.cx
o = {}
o['компаний_всего'] = e.execute('SELECT COUNT(*) FROM companies').fetchone()[0]
o['не_конкуренты'] = e.execute(
    'SELECT COUNT(*) FROM companies WHERE COALESCE(is_competitor,0)=0').fetchone()[0]
o['пройдено_архивом'] = e.execute(
    "SELECT COUNT(*) FROM stage_log WHERE stage='eis_archive'").fetchone()[0]
o['осталось'] = o['не_конкуренты'] - o['пройдено_архивом']
# перепроверка теста «имя это вёрстка» на моих записях после второго куска
import re  # noqa: E402
м = re.compile(r'опрос|статистик|карта сайта|преимуществ|органам контрол', re.I)
p = [r[0] for r in e.execute("SELECT person FROM eis_arch WHERE person<>''")]
o['мои_имена_вёрстка'] = sum(1 for x in p if м.search(x))
o['мои_имена_всего'] = len(p)
o['прежний_имена_вёрстка'] = sum(1 for r in e.execute(
    "SELECT person FROM phone_contacts WHERE source='zakupki:eis' AND person<>''")
    if м.search(r[0]))
o['прежний_строк'] = e.execute(
    "SELECT COUNT(*) FROM phone_contacts WHERE source='zakupki:eis'").fetchone()[0]
print('ИТОГ11 ' + json.dumps(o, ensure_ascii=False, indent=1), flush=True)
