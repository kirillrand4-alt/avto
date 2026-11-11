# -*- coding: utf-8 -*-
"""Разбор «писали < 15 дней» для газовых писем: компания (ИНН) vs именно этот адрес, и каким направлением
(по кампании: Meyer / КЦ). Только чтение."""
import csv, io, os, re, sqlite3
from collections import Counter
csv.field_size_limit(10 ** 9)
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
строки = читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv")
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
кампании = {i: (н or "") for i, н in s.execute("SELECT id, name FROM campaigns")}
def напр(cid):
    н = кампании.get(cid, "").lower()
    return "Meyer" if re.search(r"meyer|мейер|фса|рентген|сепарат", н) else "КЦ" if re.search(r"кц|компрессор|kc", н) else "прочее"
по_инн, по_адр = {}, {}
for inn, em, cid in s.execute("SELECT inn, lower(email), campaign_id FROM send_log WHERE outcome='sent' AND ts>=datetime('now','-15 days')"):
    if inn: по_инн.setdefault(str(inn), set()).add(напр(cid))
    по_адр.setdefault(em, set()).add(напр(cid))
комп, адр, напр_к, напр_а = set(), 0, Counter(), Counter()
for р in строки:
    inn = re.sub(r"\D", "", str(р.get("ИНН") or "")); em = (р.get("Почта") or "").strip().lower()
    if inn in по_инн:
        if inn not in комп:
            комп.add(inn); напр_к[" + ".join(sorted(по_инн[inn]))] += 1
        if em in по_адр:
            адр += 1; напр_а[" + ".join(sorted(по_адр[em]))] += 1
print("строк файлов, где компании писали < 15 дней:", sum(1 for р in строки if re.sub(r'\D', '', str(р.get('ИНН') or '')) in по_инн))
print("компаний:", len(комп), "| по направлению:", dict(напр_к))
print("из них строк, где писали ИМЕННО на этот адрес:", адр, "| по направлению:", dict(напр_а))
