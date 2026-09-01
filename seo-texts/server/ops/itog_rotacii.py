# -*- coding: utf-8 -*-
"""Итог замера ротации по серверному журналу: менялись ли адреса и как часто."""
import io
import json
import os
from collections import OrderedDict, defaultdict

ЖУРНАЛ = r"C:\sender\_ops\rotaciya-mobilnyh.jsonl"
if not os.path.exists(ЖУРНАЛ):
    print("журнала ещё нет — замер не начинался")
    raise SystemExit(0)

по_прокси = defaultdict(list)
строк = 0
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    строк += 1
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    по_прокси[z.get("прокси")].append((z.get("когда"), z.get("ip")))

print("=" * 74)
print("=== СВОДКА: РОТАЦИЯ МОБИЛЬНЫХ IP ===")
print("замеров в журнале: %d" % строк)
print("")
for п in sorted(по_прокси):
    ряд = по_прокси[п]
    смены = []
    for когда, ip in ряд:
        if not смены or смены[-1][1] != ip:
            смены.append((когда, ip))
    уник = OrderedDict((ip, None) for _, ip in ряд if ip and ip != "ошибка")
    print("прокси %s: замеров %d, разных адресов %d, смен подряд %d"
          % (п, len(ряд), len(уник), len(смены) - 1))
    print("   с %s по %s" % (ряд[0][0], ряд[-1][0]))
    for когда, ip in смены[:10]:
        print("      %s  %s" % (когда, ip))
    if len(смены) > 1:
        print("   -> IP МЕНЯЕТСЯ")
    else:
        print("   -> IP НЕ МЕНЯЛСЯ за время наблюдения")
