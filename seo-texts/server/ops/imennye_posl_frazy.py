# -*- coding: utf-8 -*-
"""Последние N записей журнала «КЦ по имени»: компания, обращение и фраза про производство (или причина отсева)."""
import io, json, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\imennye-kc.jsonl", encoding="utf-8")][-N:]
for x in з:
    if x.get("otsev"): print("ОТСЕВ", x["email"], x["otsev"][:120]); continue
    а = x["telo"].split("\n\n")
    print("#%s %s | %s\n   %s" % (x["karta"], x["email"], а[0][:60], а[1].split(". ")[0][:200]))
