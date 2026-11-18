# -*- coding: utf-8 -*-
"""Сделки компаний из kc_sc_rassylka.csv в ca-b2b-vse-sdelki.csv и составе bitrix-export-full.tar.gz: шапка, покрытие,
воронки/стадии, 8 примеров. Только чтение."""
import csv, io, os, re, tarfile, random
from collections import Counter, defaultdict
csv.field_size_limit(10 ** 9)
Д = r"C:\seostat\drop\drop-storage"; ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
ИНН = {ц(р["ИНН"]) for р in csv.DictReader(io.open(os.path.join(Д, "kc_sc_rassylka.csv"), encoding="utf-8-sig"), delimiter=";")} - {""}
r = list(csv.DictReader(io.open(os.path.join(Д, "ca-b2b-vse-sdelki.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"))
print("ca-b2b-vse-sdelki: строк", len(r), "| колонки:", list(r[0].keys())[:40])
ик = next((k for k in r[0] if re.search(r"(?i)инн", k)), None)
наши = [x for x in r if ц(x.get(ик)) in ИНН]
print("строк по нашим ИНН:", len(наши), "| компаний:", len({ц(x[ик]) for x in наши}))
for k in r[0]:
    if re.search(r"(?i)воронк|стади|направл", k): print("  ", k, Counter(x.get(k) for x in наши).most_common(8))
random.seed(3)
for x in random.sample(наши, min(8, len(наши))): print("  ", {k: v[:100] for k, v in x.items() if v})
t = tarfile.open(os.path.join(Д, "bitrix-export-full.tar.gz"))
print("bitrix-export-full:", [(m.name, m.size // 1024) for m in t.getmembers()][:40])
