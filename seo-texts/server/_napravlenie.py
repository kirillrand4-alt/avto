# -*- coding: utf-8 -*-
r"""Где в панели лежит направление КЦ/Мейер."""
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['segment'] = dict(c.execute(
    "select coalesce(segment,'(пусто)'), count(*) from recipients "
    'group by 1 order by 2 desc limit 12').fetchall())
итог['ящики_по_доменам'] = dict(c.execute(
    "select substr(mailbox_id, instr(mailbox_id,'@')+1) д, count(*) "
    'from messages where sent_at is not null group by 1 order by 2 desc limit 15').fetchall())
# что в extra_json
r = c.execute("select extra_json from recipients where coalesce(extra_json,'')<>'' limit 1").fetchone()
итог['пример_extra'] = (r[0][:400] if r else 'пусто')
# ключи extra по всей базе
ключи = {}
for (s,) in c.execute("select extra_json from recipients "
                      "where coalesce(extra_json,'')<>'' limit 3000"):
    try:
        for k in json.loads(s).keys():
            ключи[k] = ключи.get(k, 0) + 1
    except Exception:
        pass
итог['ключи_extra'] = dict(sorted(ключи.items(), key=lambda x: -x[1])[:14])
c.close()
o = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
итог['division_в_обзвоне'] = dict(o.execute(
    "select coalesce(division,'(пусто)'), count(*) from obzvon group by 1").fetchall())
o.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
