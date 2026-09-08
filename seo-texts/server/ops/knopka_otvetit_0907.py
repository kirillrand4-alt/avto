# -*- coding: utf-8 -*-
"""Только чтение: что делает кнопка «Ответить на это письмо» в ленте."""
import io
import os
import re

НАЙТИ = ("Ответить на это письмо", "reply_sent", "otvetit", "reply_to_lead",
         "send_reply")
файлы = []
for корень in (r"C:\sender\server", r"C:\sender\web", r"C:\sender\sender"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith((".py", ".html", ".js", ".jinja", ".j2")):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            метки = [н for н in НАЙТИ if н in т]
            if метки:
                файлы.append((п, т, метки))

print("=== ФАЙЛЫ ===")
for п, _, м in файлы:
    print("  %-52s %s" % (п.replace(r"C:\sender", "")[:52], ",".join(м)))

# сам обработчик отправки ответа
for п, т, _ in файлы:
    if not п.endswith(".py"):
        continue
    for м in re.finditer(r"reply_sent", т):
        нач = т.rfind("\ndef ", 0, м.start())
        нач2 = т.rfind("\n    def ", 0, м.start())
        нач = max(нач, нач2)
        нач = нач if нач > 0 else max(0, м.start() - 2200)
        print("\n" + "=" * 16 + " %s " % п.replace(r"C:\sender", "") + "=" * 16)
        print(т[нач:м.start() + 700])
        break
