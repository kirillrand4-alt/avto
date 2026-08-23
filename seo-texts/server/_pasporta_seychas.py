# -*- coding: utf-8 -*-
r"""Сколько паспортов сейчас: готовых, полных и что в работе."""
import json
import sqlite3
import time

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
д = {
    'ГОТОВЫХ_формат2': c.execute(
        "select count(*) from site_facts where coalesce(facts_json,'')<>'' "
        'and coalesce(format,0)>=2').fetchone()[0],
    'ПОЛНЫХ_с_продукцией': c.execute(
        "select count(*) from site_facts where coalesce(format,0)>=2 "
        "and facts_json like '%\"продукция\": [\"%'").fetchone()[0],
    'записей_всего': c.execute('select count(*) from site_facts').fetchone()[0],
    'пустых_карточек': c.execute(
        "select count(*) from site_facts where coalesce(facts_json,'')=''"
    ).fetchone()[0],
}
for ч in (1, 6):
    п = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - ч * 3600))
    д['за_%dч' % ч] = c.execute(
        "select count(*) from site_facts where ts>? and coalesce(facts_json,'')<>''",
        (п,)).fetchone()[0]
c.close()
print(json.dumps(д, ensure_ascii=False, indent=1))
