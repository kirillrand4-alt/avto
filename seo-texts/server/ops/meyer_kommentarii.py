# -*- coding: utf-8 -*-
"""Что за «комментарий менеджера» у подходящих компаний (meyer-provaly.jsonl): текст после «Комментарий:» в поле
причины провала. Сколько — только ссылки (checko/agroserver/list-org — справки о компании), сколько — живой текст;
примеры с маскированием телефонов/почт. Только чтение."""
import io, json, random, re
from collections import Counter
сч = Counter(); живые = []
for с in io.open(r"C:\sender\_ops\meyer-provaly.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if not x["kat"].startswith("ПОДХОДИТ"): continue
    ком = [p.split("Комментарий:", 1)[1] for p in x["prichiny"] if "Комментарий:" in p]
    if not ком: сч["нет комментария"] += 1; continue
    т = " ".join(ком)
    без = re.sub(r"\[/?url[^\]]*\]|https?://\S+|\[/?[a-zA-Z]+\]", " ", т)
    без = re.sub(r"\s+", " ", без).strip()
    if len(без) < 8: сч["только ссылка (справка о компании)"] += 1; continue
    сч["живой текст"] += 1; живые.append(без)
print(dict(сч))
random.seed(7)
маска = lambda s: re.sub(r"\S+@\S+", "<почта>", re.sub(r"\+?\d[\d\s\-()]{8,}\d", "<тел>", s))
print("\n20 случайных живых комментариев (обрезано до 160 знаков):")
for t in random.sample(живые, min(20, len(живые))): print(" -", маска(t)[:160])
