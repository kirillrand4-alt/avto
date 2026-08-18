# -*- coding: utf-8 -*-
"""Из каких доменов наш непроверенный остаток и что проверка по ним вообще даёт."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
верд = {str(r[0]).lower(): r[1] for r in s.execute('select email, verdict from addr_probe')}
наши = []
for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                        "from recipients where extra_json like '%Партия 935%'"):
    if not em or em in верд:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if 'Партия 935' in [str(g) for g in (d.get('gruppy') or [])]:
        наши.append(em)
s.close()
по_дом = {}
for a in set(наши):
    по_дом[a.rsplit('@', 1)[-1]] = по_дом.get(a.rsplit('@', 1)[-1], 0) + 1
топ = sorted(по_дом.items(), key=lambda kv: -kv[1])[:8]
# что исторически давала проверка по этим доменам
итог = {'без_вердикта': len(set(наши)), 'доменов': len(по_дом), 'топ_доменов': топ}
статистика = {}
for дом, _ in топ[:4]:
    счёт = {}
    for адрес, в in верд.items():
        if адрес.endswith('@' + дом):
            счёт[в] = счёт.get(в, 0) + 1
    статистика[дом] = dict(sorted(счёт.items(), key=lambda kv: -kv[1]))
итог['что_давала_проверка_по_этим_доменам'] = статистика
итог['часов_при_3_на_домен_за_10_минут'] = round(
    max((n for _, n in топ), default=0) / 18.0, 1)
print(json.dumps(итог, ensure_ascii=False, indent=1))
