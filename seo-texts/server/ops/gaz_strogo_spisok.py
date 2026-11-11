# -*- coding: utf-8 -*-
"""Список подтверждённых строгой проверкой (gaz-kc-strogo.jsonl ok=true): ИНН | отрасль | компания | продукция |
оборудование | почему. В файл gaz-strogo-spisok.txt + копия на дроп. Только чтение."""
import csv, io, json, os, re, shutil
csv.field_size_limit(10 ** 9)
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
база = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-ZALIVKA.csv") + читать("CA-ENGER-ZALIVKA-kompanii.csv")}
сайт = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
стр = {}
for с in io.open(r"C:\sender\_ops\gaz-kc-strogo.jsonl", encoding="utf-8"):
    з = json.loads(с); стр[з["inn"]] = з
вых = io.open(r"C:\sender\_ops\gaz-strogo-spisok.txt", "w", encoding="utf-8")
for и, з in sorted(стр.items(), key=lambda x: x[1]["otr"]):
    if not з["ok"]: continue
    р, с = база.get(и, {}), сайт.get(и, {})
    вых.write("%s | %s | %s | %s | обор: %s | %s\n" % (и, з["otr"][:18], (р.get("Компания") or "")[:40], (р.get("Продукция") or "")[:120],
                                                    (с.get("Оборудование, линии") or "-")[:70], з["pochemu"][:90]))
вых.close()
shutil.copy2(r"C:\sender\_ops\gaz-strogo-spisok.txt", os.path.join(ДРОП, "gaz-strogo-spisok.txt"))
print("готово")
