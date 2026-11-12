# -*- coding: utf-8 -*-
"""Где взять связь сделка/компания Битрикса → ИНН: форма sdelki-inn.json, sdelki-napr-1410.json, ca-b2b-vse-sdelki.csv,
состав bitrix-export-full.tar.gz. Только чтение, без контактов."""
import io, json, os, tarfile, csv
Д = r"C:\seostat\drop\drop-storage"
for имя in ("sdelki-inn.json", "sdelki-napr-1410.json"):
    д = json.load(io.open(os.path.join(Д, имя), encoding="utf-8"))
    эл = list(д.items())[:2] if isinstance(д, dict) else д[:2]
    print(имя, type(д).__name__, len(д), json.dumps(эл, ensure_ascii=False)[:400])
r = csv.reader(io.open(os.path.join(Д, "ca-b2b-vse-sdelki.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";")
print("ca-b2b-vse-sdelki.csv шапка:", next(r)[:30])
t = tarfile.open(os.path.join(Д, "bitrix-export-full.tar.gz"))
чл = t.getmembers(); print("bitrix-export-full: файлов", len(чл))
for m in чл[:60]: print("  ", m.name, m.size)
