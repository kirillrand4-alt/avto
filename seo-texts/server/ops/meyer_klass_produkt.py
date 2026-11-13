# -*- coding: utf-8 -*-
"""Сколько размеченных компаний Meyer получили продукт / оборудование / конкурента, топ продуктов. Только чтение."""
import io, json
from collections import Counter
з = [json.loads(с) for с in io.open(r"C:\sender\_ops\meyer-provaly-klass.jsonl", encoding="utf-8")]
з = [x for x in з if x.get("shablon") != "NE_PISAT"]
print("пишем:", len(з), "| с продуктом:", sum(1 for x in з if (x.get("produkt") or "").strip()), "| с оборудованием:", sum(1 for x in з if x.get("oborud")), "| с конкурентом:", sum(1 for x in з if (x.get("konkurent") or "").strip()))
print("топ продуктов:", Counter((x.get("produkt") or "").strip().lower() for x in з if (x.get("produkt") or "").strip()).most_common(15))
