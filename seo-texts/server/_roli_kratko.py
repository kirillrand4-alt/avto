# -*- coding: utf-8 -*-
r"""Коротко: у каких источников телефонов роль есть, а у каких нет."""
import json
import sqlite3

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
строки = []
for r in c.execute(
        "select coalesce(source,'(пусто)') s, count(*) n, "
        "sum(case when coalesce(role,'') not in ('','общий') then 1 else 0 end) rl "
        'from phone_contacts group by s order by n desc limit 8'):
    строки.append('%-30s всего %6d  с ролью %5d  (%4.1f%%)'
                  % (str(r[0])[:30], r[1], r[2], 100.0 * r[2] / max(1, r[1])))
c.close()
print('\n'.join(строки))
