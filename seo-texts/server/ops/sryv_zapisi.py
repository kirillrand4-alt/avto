# -*- coding: utf-8 -*-
"""_eto_sryv / _zapisat_sryv: как определяется срыв и что записано за сегодня."""
import io
import json
import os
import re
import time

П = r"C:\sender\sender\review_lenses.py"
s = io.open(П, encoding="utf-8", errors="replace").read()
for имя in ("_eto_sryv", "_zapisat_sryv"):
    i = s.find("def %s" % имя)
    if i < 0:
        print("нет функции %s" % имя)
        continue
    j = s.find("\ndef ", i + 10)
    print("=== %s ===" % имя)
    print(s[i:j if j > 0 else i + 2600][:2600])
    print("")

# куда пишет
м = re.search(r"(?:ФАЙЛ|ЖУРНАЛ|_СРЫВ\w*)\s*=\s*r?['\"]([^'\"]+)['\"]", s)
пути = set(re.findall(r"r['\"](C:\\\\[^'\"]+)['\"]", s))
пути |= set(re.findall(r"r['\"](C:\\[^'\"]+)['\"]", s))
print("=== пути в файле ===")
for п in sorted(пути):
    print("   %s   %s" % (п, "есть" if os.path.exists(п) else "НЕТ"))

for п in sorted(пути):
    if п.endswith(".jsonl") and os.path.exists(п):
        строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
        сег = [x for x in строки[-4000:] if "2026-09-01" in x or "09-01" in x]
        print("")
        print("=== %s: всего %d строк, сегодняшних в хвосте %d ==="
              % (os.path.basename(п), len(строки), len(сег)))
        for x in (сег or строки)[-12:]:
            try:
                z = json.loads(x)
                print("   " + json.dumps({k: (str(v)[:80]) for k, v in z.items()},
                                         ensure_ascii=False)[:300])
            except Exception:  # noqa: BLE001
                print("   " + x[:250])
