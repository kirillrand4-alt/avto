# -*- coding: utf-8 -*-
"""Почему фразы модели не прошли (kc-sc-kartochki.jsonl, otsev «фраза модели»). Только чтение."""
import io, json
for с in io.open(r"C:\sender\_ops\kc-sc-kartochki.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if str(x.get("otsev", "")).startswith("фраза"): print(x["kluch"], "|", x["otsev"][:200])
