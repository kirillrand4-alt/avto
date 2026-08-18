# -*- coding: utf-8 -*-
"""Какие вердикты приходят по адресам партии — чтобы знать, что чинить потом."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
верд = {str(r[0]).lower(): r[1] for r in s.execute('select email, verdict from addr_probe')}
свои, счёт = 0, {}
мёртвые = []
for em, ex, инн in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,''), "
                             "coalesce(inn,'') from recipients "
                             "where extra_json like '%Партия 935%'"):
    if not em:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if 'Партия 935' not in [str(g) for g in (d.get('gruppy') or [])]:
        continue
    свои += 1
    в = верд.get(em, '(ещё не проверен)')
    счёт[в] = счёт.get(в, 0) + 1
    if в == 'нет ящика' and len(мёртвые) < 5:
        мёртвые.append({'инн': инн, 'адрес': em})
s.close()
print(json.dumps({'адресов_партии': свои,
                  'по_вердиктам': dict(sorted(счёт.items(), key=lambda kv: -kv[1])),
                  'примеры_мёртвых': мёртвые}, ensure_ascii=False, indent=1))
