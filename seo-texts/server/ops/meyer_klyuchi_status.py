# -*- coding: utf-8 -*-
"""Все записи журнала партии Meyer по ключам: meyer_klyuchi_status.py k1,k2,... Только чтение."""
import io, json, sys
кл = set(sys.argv[1].split(","))
for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8"):
    if с.strip():
        з = json.loads(с)
        if з["kluch"] in кл: print(з["kluch"], з["status"], з.get("ruchnaya_pravka", ""), з["ts"], з["tema"])
