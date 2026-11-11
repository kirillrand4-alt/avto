# -*- coding: utf-8 -*-
"""Профиль CSV с дропа (на сервере, контакты наружу не печатаются): колонки, заполненность,
для коротких категориальных колонок — топ значений; для прочих — 2 примера, где e-mail/телефоны/ФИО
замаскированы. Только чтение.
    profil_csv_drop.py <имя_на_дропе> [--kolonka=Имя]  (вторая форма — топ-40 значений одной колонки)"""
import csv, io, re, sys
from collections import Counter
csv.field_size_limit(10 ** 9)
п = r"C:\seostat\drop\drop-storage" + "\\" + sys.argv[1]
сыр = io.open(п, encoding="utf-8-sig", errors="replace").read(200000)
разд = ";" if сыр.count(";") > сыр.count(",") else ","
стр = list(csv.DictReader(io.open(п, encoding="utf-8-sig", errors="replace"), delimiter=разд))
ш = list(стр[0].keys()) if стр else []
def маска(v):
    v = re.sub(r"[\w.+-]+@[\w.-]+", "<email>", v)
    v = re.sub(r"\+?\d[\d\s()\-]{8,}\d", "<тел>", v)
    return v
КОЛ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--kolonka=")), None)
if КОЛ:
    сч = Counter(маска(str(r.get(КОЛ) or ""))[:90] for r in стр)
    print("колонка «%s», уникальных %d:" % (КОЛ, len(сч)))
    ДЛ = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--dl=")), "90"))
    сч = Counter(маска(str(r.get(КОЛ) or ""))[:ДЛ] for r in стр)
    for k, n in сч.most_common(40): print("  %6d  %s" % (n, k))
    sys.exit(0)
print("первые колонки:", ш[:12])
print("файл %s | разделитель %r | строк %d | колонок %d" % (sys.argv[1], разд, len(стр), len(ш)))
for h in ш:
    зн = [str(r.get(h) or "").strip() for r in стр]
    непуст = [v for v in зн if v]
    ун = Counter(непуст)
    if not непуст:
        print("  %-45s пусто" % h[:45]); continue
    доля = 100.0 * len(непуст) / len(стр)
    if len(ун) <= 25:
        print("  %-45s %5.1f%% | %d знач: %s" % (h[:45], доля, len(ун), "; ".join("%s=%d" % (маска(k)[:30], n) for k, n in ун.most_common(8))))
    else:
        пр = [маска(v)[:70] for v in непуст[:2]]
        print("  %-45s %5.1f%% | уник %d | пр: %s" % (h[:45], доля, len(ун), " ‖ ".join(пр)))
