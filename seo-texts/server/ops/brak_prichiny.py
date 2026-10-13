# -*- coding: utf-8 -*-
"""Причины брака за день: сколько и по каким шаблонам (журнал 9000)."""
import io
import json
import re
import sys
from collections import Counter
ДЕНЬ = sys.argv[1] if len(sys.argv) > 1 else "2026-10-13"
св, прим, всего, ок = Counter(), {}, 0, 0
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з.get("этап") != "итог" or з.get("день") != ДЕНЬ:
        continue
    всего += 1
    if з.get("ок"):
        ок += 1
        continue
    б = " ".join(str(x) for x in з.get("брак") or [])
    к = re.sub(r"[«\"'].*", "", б)[:70]
    if "НЕ ПОКУПАТЕЛЬ" in б:
        поч = б.split("НЕ ПОКУПАТЕЛЬ:", 1)[-1].strip()
        к = ("НЕ ПОКУПАТЕЛЬ / про письмо: " if re.search(r"обеща|небезопасн|приписан|сказано то|в письме|формулир", поч)
             else "НЕ ПОКУПАТЕЛЬ / про компанию: ") + ("переставить на kc" if "переставить" in б else "линза")
    св[к] += 1
    прим.setdefault(к, []).append("%s | %s" % (str(з.get("имя"))[:28], б[:150]))
print("день %s: итогов %d, годных %d" % (ДЕНЬ, всего, ок))
for к, n in св.most_common(14):
    print("%4d  %s" % (n, к))
    for п in прим[к][:2]:
        print("        " + п)
print("=== ПРИЧИНЫ БРАКА ===")
