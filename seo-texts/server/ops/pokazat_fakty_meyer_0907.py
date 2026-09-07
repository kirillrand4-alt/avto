# -*- coding: utf-8 -*-
"""Только чтение: содержимое базы знаний meyer."""
import io
import json

for п in (r"C:\sender\meyer_glossary.json", r"C:\sender\meyer-facts.json"):
    print("\n" + "=" * 20 + " " + п + " " + "=" * 20)
    try:
        d = json.load(io.open(п, encoding="utf-8"))
        print(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception as e:
        print("ошибка:", e)
