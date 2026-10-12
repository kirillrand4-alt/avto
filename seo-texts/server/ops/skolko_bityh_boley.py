# -*- coding: utf-8 -*-
"""Скольким компаниям партии достанется боль, которую потом бракует гейт.

Коды приоритетнее отраслей, поэтому спорные строки карты по ОКВЭД
(10.1 «кость, хрящ», 10.6 «ручная переборка», 46 «рекламации») получают
все, у кого такой код, — независимо от исправленного отраслевого слоя.
"""
import glob
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AL                               # noqa: E402

ЛОВУШКИ = [
    ("кость/хрящ/косточки", re.compile(
        r"(?i)\bкост(ь|и|ью|ей|ям|ями|ях|очк\w*|н\w+)\b|хрящ")),
    ("ручной труд", re.compile(
        r"(?i)ручн\w+\s+(труд|переборк|сортировк|отбор)|вручную")),
    ("рекламации/страшилка", re.compile(r"(?i)\bрекламац|\bштраф|репутаци")),
    ("деньги", re.compile(r"(?i)\bмарж|\bцен[аыу]\b|\bстоимост")),
]

pains = AL._okved_pains()
битые = {}
for раздел in ("meyer", "meyer_foto", "meyer_rentgen", "_по_отрасли",
               "_по_умолчанию"):
    т = pains.get(раздел) or {}
    if not isinstance(т, dict):
        continue
    for ключ, текст in т.items():
        для = [имя for имя, рег in ЛОВУШКИ if рег.search(str(текст))]
        if для:
            битые[(раздел, ключ)] = (для, текст)
print("спорных строк в карте болей: %d" % len(битые))
for (раздел, ключ), (для, текст) in sorted(битые.items()):
    print("   %-14s %-10s %-24s %s"
          % (раздел, ключ, ",".join(для), str(текст)[:70]))

компании = []
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    компании.extend(json.load(io.open(п, encoding="utf-8")).get("компании") or [])

попало = Counter()
всего_битых = 0
for к in компании:
    коды = [c.strip() for c in
            (str(к.get("okved") or "") + "," + str(к.get("okved_all") or "")
             ).replace("|", ",").split(",") if c.strip()]
    коды = [c.split()[0] if " " in c else c for c in коды]
    боль, откуда = AL.боль_по_кодам(коды, "meyer", к.get("otrasl"))
    для = [имя for имя, рег in ЛОВУШКИ if рег.search(str(боль))]
    if для:
        всего_битых += 1
        for имя in для:
            попало[имя] += 1
        попало["    ↳ по коду %s" % (откуда or "(отрасль)")] += 1

print("")
print("--- скольким компаниям книг достанется такая боль ---")
for имя, n in попало.most_common(12):
    print("   %-34s %5d" % (имя, n))
print("")
print("=" * 70)
print("=== БОЛИ, КОТОРЫЕ БРАКУЕТ СОБСТВЕННЫЙ ГЕЙТ ===")
print("   компаний в книгах:          %5d" % len(компании))
print("   получат спорную боль:       %5d" % всего_битых)
print("   доля:                       %5.1f%%"
      % (100.0 * всего_битых / max(len(компании), 1)))
