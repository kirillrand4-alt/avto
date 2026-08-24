# -*- coding: utf-8 -*-
r"""Сколько сейчас в группе и сколько всего получателей — ход заливки."""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
d = {'строк_в_группе': c.execute(
    "select count(*) from recipients where extra_json like '%Партия 935%'"
).fetchone()[0],
    'всего_получателей': c.execute(
        'select count(*) from recipients').fetchone()[0]}
инн = set()
for и, ex in c.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                       'from recipients'):
    if 'Партия 935' in ex:
        ц = ''.join(x for x in str(и) if x.isdigit())
        if ц:
            инн.add(ц)
d['компаний_в_группе'] = len(инн)
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
