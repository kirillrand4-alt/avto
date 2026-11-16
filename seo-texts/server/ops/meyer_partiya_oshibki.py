# -*- coding: utf-8 -*-
"""Письма партии «провалы Meyer» со статусом ошибка/не писать: какая линза и почему. Только чтение.  [--n=20]"""
import io, json, sys
n = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--n=")), "20"))
зз = [json.loads(с) for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8")]
if "--poslednie" in sys.argv: зз = зз[::-1]
for з in зз:
    if з["status"] == "ок": continue
    n -= 1
    if n < 0: break
    print("=== %s | %s | %s | откат %s" % (з["status"], з["shablon"], з["kompaniya"], з.get("otkat")))
    for к in ("tehnolog", "skeptik", "redaktor"):
        if з[к].get("verdict") != "верно": print("  %s: %s — %s" % (к, з[к].get("verdict"), (з[к].get("pochemu") or "")[:300]))
