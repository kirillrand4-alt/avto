# -*- coding: utf-8 -*-
"""Тексты писем опыта КЦ (НОВЫЙ): тема и тело как ушли."""
import io
import json
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
for с in io.open(r"C:\sender\_ops\opyt-kc.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з["вариант"] != "НОВЫЙ":
        continue
    р = c.execute("SELECT subject, body_rendered FROM messages WHERE id=?", (з["mid"],)).fetchone()
    print("== %s -> %s\nТема: %s\n%s\n" % (з["ящик"], з["email"], р[0], р[1]))
print("=== ПИСЬМА ОПЫТА ===")
