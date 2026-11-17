# -*- coding: utf-8 -*-
"""Полные тексты писем «ошибка» из журнала партии Meyer (последняя запись по ключу) — для ручной правки. Только чтение."""
import io, json, sys
ДО = int(sys.argv[1]) if len(sys.argv) > 1 else 99  # печатать только первые N (вывод раннера режется с начала)
н = 0
ж = {}
for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8"):
    if с.strip(): з = json.loads(с); ж[з["kluch"]] = з
for з in ж.values():
    if з.get("status") != "ошибка" or "инистерств" in (з.get("kompaniya") or "") or "инсельхоз" in (з.get("kompaniya") or ""): continue
    н += 1
    if н > ДО: break
    if н <= (int(sys.argv[2]) if len(sys.argv) > 2 else 0): continue
    print(json.dumps({к: з.get(к) for к in ("kluch", "kompaniya", "email", "fio", "obrashchenie", "produkt", "rentgen", "shablon", "lichnaya", "tema", "pismo")}, ensure_ascii=False))
    print("ПРИЧИНЫ:", {к: з.get(к) for к in ("tehnolog", "skeptik", "redaktor")}, "\n")
