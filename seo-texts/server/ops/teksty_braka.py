# -*- coding: utf-8 -*-
"""Последние тексты писем, ушедших в брак по шаблону причины (журнал 9000).

    teksty_braka.py "<кусок причины>" [n=4]
"""
import io
import json
import sys
К = sys.argv[1]
N = int(dict(а.split("=", 1) for а in sys.argv[2:] if "=" in а).get("n", "4"))
зап = []
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з.get("этап") == "итог" and К in " ".join(map(str, з.get("брак") or [])):
        зап.append(з)
print("всего с этой причиной: %d; ключи: %s" % (len(зап), sorted(зап[-1].keys()) if зап else "-"))
for з in зап[-N:]:
    тело = ""
    for k in ("тело_брака", "черновик", "письмо", "body", "текст", "draft"):
        if з.get(k):
            тело = з[k] if isinstance(з[k], str) else json.dumps(з[k], ensure_ascii=False)
            break
    print("--- %s | %s" % (з.get("имя"), з.get("брак")))
    print(тело[-700:])
print("=== ТЕКСТЫ БРАКА ===")
