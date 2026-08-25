# -*- coding: utf-8 -*-
"""Что уже вытащено из каталога: страницы, компании, полнота контактов."""
import io
import json
import os
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\belarus\katalog-razbor.jsonl"
если = os.path.exists(ЖУРНАЛ)
print("журнал: %s" % ("есть" if если else "нет"))
if not если:
    raise SystemExit(0)

страницы, компании = {}, []
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") != "готово":
        continue
    страницы[int(з["страница"])] = int(з.get("компаний") or 0)
    for к in (з.get("компании") or []):
        к["_страница"] = з["страница"]
        компании.append(к)

print("страниц разобрано: %d, компаний найдено: %d"
      % (len(страницы), len(компании)))
пусто = sorted(с for с, н in страницы.items() if not н)
print("страницы без карточек: %s%s"
      % (пусто[:14], " …" if len(пусто) > 14 else ""))

if компании:
    полнота = Counter()
    for к in компании:
        for поле in ("почта", "сайт", "телефон", "чем_занимается"):
            if str(к.get(поле) or "").strip():
                полнота[поле] += 1
    print("\n=== ПОЛНОТА ===")
    for поле in ("почта", "сайт", "телефон", "чем_занимается"):
        print("   %-16s %3d из %d" % (поле, полнота[поле], len(компании)))
    print("\n=== ПЕРВЫЕ КАРТОЧКИ ===")
    for к in компании[:3]:
        print("   стр.%-3s %-42s" % (к.get("_страница"),
                                     str(к.get("название") or "")[:42]))
        print("        %-30s %-26s %s"
              % (str(к.get("почта") or "-")[:30], str(к.get("сайт") or "-")[:26],
                 str(к.get("город") or "-")[:20]))
        if к.get("чем_занимается"):
            print("        %s" % str(к["чем_занимается"])[:96])
