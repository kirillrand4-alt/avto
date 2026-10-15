# -*- coding: utf-8 -*-
"""Порог автопаузы направления по спам-отказам (gates.otkaz_stop_napravlenie)
в sender.yaml: porog_spam.py [N]  — без N только показать. Бэкап .bak-<ts>.
Владелец 15.10: «подними порог до 20 спам-отбивок». Нужен перезапуск службы."""
import io
import re
import shutil
import sys
import time
П = r"C:\sender\sender.yaml"
т = io.open(П, encoding="utf-8").read()
м = re.search(r"(?m)^gates:\s*\n((?:[ \t]+.*\n|\s*\n)*)", т)
print("секция gates:\n" + (м.group(0)[:800] if м else "НЕТ"))
if len(sys.argv) > 1 and м:
    N = int(sys.argv[1])
    shutil.copy2(П, П + ".bak-%d" % int(time.time()))
    if re.search(r"(?m)^[ \t]+otkaz_stop_napravlenie:", т):
        т = re.sub(r"(?m)^([ \t]+otkaz_stop_napravlenie:)\s*\S*", r"\g<1> %d" % N, т)
    else:
        отступ = re.match(r"[ \t]+", м.group(1)).group(0) if re.match(r"[ \t]+", м.group(1)) else "  "
        т = т.replace(м.group(0), "gates:\n%sotkaz_stop_napravlenie: %d   # владелец 15.10\n" % (отступ, N) + м.group(0)[len("gates:\n"):], 1)
    io.open(П, "w", encoding="utf-8").write(т)
    import yaml
    yaml.safe_load(io.open(П, encoding="utf-8"))
    print("записано: otkaz_stop_napravlenie = %d (yaml валиден)" % N)
print("=== ПОРОГ СПАМ ===")
