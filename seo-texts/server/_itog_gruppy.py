# -*- coding: utf-8 -*-
"""Итоговый состав группы после догруза и снятия дублей."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
строки = [dict(r) for r in s.execute(
    "select coalesce(inn,'') inn, coalesce(company_name,'') nm, "
    "coalesce(okved,'') ok, coalesce(region,'') reg, coalesce(segment,'') seg, "
    "coalesce(contact_name,'') cn, pxr, priority_total pt, coalesce(tz,'') tz "
    "from recipients where extra_json like '%Партия 935%'")]
счёт = {}
for r in строки:
    if r['inn']:
        счёт[r['inn']] = счёт.get(r['inn'], 0) + 1
итог = {'получателей': len(строки), 'компаний': len(счёт),
        'компаний_с_дублями': sum(1 for v in счёт.values() if v > 1),
        'заполнено': {}}
for п, к in (('inn', 'inn'), ('nm', 'company_name'), ('ok', 'okved'),
             ('reg', 'region'), ('seg', 'segment'), ('cn', 'contact_name'),
             ('tz', 'tz')):
    итог['заполнено'][к] = sum(1 for r in строки if r[п])
итог['заполнено']['pxr'] = sum(1 for r in строки if r['pxr'] is not None)
итог['заполнено']['priority_total'] = sum(1 for r in строки if r['pt'] is not None)
итог['группы_в_панели'] = []
гр = {}
for ex, in s.execute("select coalesce(extra_json,'') from recipients"):
    if 'gruppy' not in ex:
        continue
    try:
        for g in (json.loads(ex).get('gruppy') or []):
            гр[g] = гр.get(g, 0) + 1
    except Exception:  # noqa: BLE001
        pass
итог['группы_в_панели'] = sorted(гр.items(), key=lambda kv: -kv[1])[:6]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
