# -*- coding: utf-8 -*-
import glob, io, json, os
ж = r"C:\sender\_ops\sdelki-rekvizity.jsonl"
n = 0
for с in io.open(ж, encoding="utf-8", errors="ignore"):
    с = с.strip()
    if not с:
        continue
    d = json.loads(с)
    if d.get("ogrn"):
        print(json.dumps(d, ensure_ascii=False, indent=1)[:1200])
        n += 1
    if n >= 2:
        break
print("\nвсего строк: %d" % sum(1 for _ in io.open(ж, encoding="utf-8",
                                                   errors="ignore")))
for п in sorted(glob.glob(r"C:\sender\_ops\zalit_iz_zhurnala-*"))[-2:]:
    т = io.open(п, encoding="utf-8", errors="ignore").read()
    print("\n--- %s (%d б) ---\n%s" % (os.path.basename(п), len(т), т[-400:]))
