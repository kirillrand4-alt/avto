# -*- coding: utf-8 -*-
"""patch_otchyoty_store.py"""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\store.py"
МЕТКА = "event_type <> 'otchet'"
ЗАМЕНЫ = json.loads(r'''[["            sql.append(\"AND event_type IN (%s)\" % \",\".join(\"?\" for _ in vals))\n            params.extend(vals)\n        for col, val in ((\"campaign_id\", campaign_id), (\"provider\", provider),", "            params.extend(vals)\n        else:\n            # МАШИННЫЕ ОТЧЁТЫ НЕ ПОКАЗЫВАЕМ. Агрегированные отчёты DMARC шлёт\n            # каждый крупный почтовик раз в сутки, а тело у них — zip: в ленте\n            # это выглядело строкой «PK□□□□□CJ ]юд⊥пЙ□□□u□□□8□□□google.com!...»\n            # и занимало полэкрана (28.08: 106 отчётов и 48 двоичных обрывков\n            # из 253 записей «входящее вне переписки»). В журнале они остаются\n            # — спросить их можно явным event_type='otchet'.\n            sql.append(\"AND event_type <> 'otchet'\")\n        for col, val in ((\"campaign_id\", campaign_id), (\"provider\", provider),"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
