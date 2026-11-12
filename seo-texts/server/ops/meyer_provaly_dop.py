# -*- coding: utf-8 -*-
"""Добор для анализа провалов Meyer: какие ещё файлы дают сделка→ИНН; распределение «причины» (до «|») и воронок
у проваленных сделок файла. Только чтение."""
import csv, io, json, os, re
from collections import Counter
Д = r"C:\seostat\drop\drop-storage"
csv.field_size_limit(10 ** 9)
r = csv.DictReader(io.open(os.path.join(Д, "ca-b2b-vse-sdelki.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";")
кол = [k for k in r.fieldnames if "ID" in k or "Сделк" in k]; print("ca-b2b-vse-sdelki колонки сделок:", кол)
n = 0; ids = 0
for р in r:
    n += 1
    for k in кол:
        ids += len(re.findall(r"\b\d{5,7}\b", р.get(k) or ""))
print("  строк", n, "ID сделок в них", ids)
for имя in ("meyer7-sdelki-yur.jsonl", "meyer7-sdelki-yur-model.jsonl"):
    п = os.path.join(Д, имя)
    if os.path.exists(п):
        с = io.open(п, encoding="utf-8").readline(); print(имя, "пример ключей:", list(json.loads(с).keys())[:20], sum(1 for _ in io.open(п, encoding="utf-8")))
for имя in ("kc-sc-sdelki-0910.csv", "meyer7-sdelki-aktivnye.tsv"):
    п = os.path.join(Д, имя)
    if os.path.exists(п): print(имя, "шапка:", io.open(п, encoding="utf-8-sig", errors="replace").readline()[:300])
ряды = list(csv.DictReader(io.open(os.path.join(Д, "meyer-kontakty-sdelok.csv"), encoding="utf-8-sig", errors="replace"), delimiter=";"))
сд = {}
for р in ряды: сд.setdefault(р["DEAL_ID"], р)
пров = [р for р in сд.values() if р["СТАТУС"] == "Провалена"]
print("провалов:", len(пров), "по воронкам:", Counter(р["ВОРОНКА"] for р in пров))
print("голова причины (до «|»):", Counter((р["ПРИЧИНА_ПРОВАЛА"] or "").split("|")[0].strip()[:60] for р in пров).most_common(30))
print("с комментарием:", sum(1 for р in пров if "Комментарий:" in (р["ПРИЧИНА_ПРОВАЛА"] or "")))
