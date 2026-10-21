# -*- coding: utf-8 -*-
"""Последние N дописанных писем КЦ-1 (_ops/dopisannye-kc1.jsonl): гейт, тема, текст."""
import io
import json
import sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\dopisannye-kc1.jsonl", encoding="utf-8")]
for x in з[-N:]:
    print("==== %s | гейт: %s | очередь: %s\nТема: %s\n\n%s\n" % (x.get("имя"), x.get("гейт"), x.get("статус_очереди") or x.get("review_id"), x.get("тема"), x.get("тело")))
