# -*- coding: utf-8 -*-
"""Дописать в _ops/partiya-deshevye.json компании, где модель отказывала (возврат в пул 13.10)."""
import io
import json
ПУТЬ = r"C:\sender\_ops\partiya-deshevye.json"
сп = json.load(io.open(ПУТЬ, encoding="utf-8"))
отк = []
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("этап") == "итог" and "I can" in json.dumps(z.get("брак") or [], ensure_ascii=False):
        if z.get("recipient_id") not in отк:
            отк.append(z.get("recipient_id"))
новые = [r for r in отк if r and r not in сп]
json.dump(сп + новые, io.open(ПУТЬ, "w", encoding="utf-8"))
print("в списке было %d, добавлено отказавших %d" % (len(сп), len(новые)))
print("=== СПИСОК + ОТКАЗАВШИЕ ===")
