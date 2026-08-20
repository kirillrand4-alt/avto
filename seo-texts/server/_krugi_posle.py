# -*- coding: utf-8 -*-
r"""Что цикл фактов делает после перезапуска: круги и колонка переразборов."""
import json
import sqlite3
import time

time.sleep(120)
d = {}
with open(r'C:\sender\server\fakty_cikl.log', encoding='utf-8', errors='replace') as f:
    строки = [s.strip() for s in f if s.strip()]
d['круги'] = [s[:200] for s in строки[-6:]]
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
d['колонка_pererazborov'] = 'pererazborov' in [
    x[1] for x in c.execute('PRAGMA table_info(site_facts)')]
п = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - 600))
d['паспортов_за_10мин'] = c.execute(
    "select count(*) from site_facts where ts>? and coalesce(facts_json,'')<>''",
    (п,)).fetchone()[0]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
