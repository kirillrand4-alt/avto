# -*- coding: utf-8 -*-
"""Примеры починки яруса C: причина, изменённые абзацы было/стало. Только чтение.
    dopisannye_primery.py [N=3]"""
import difflib
import io
import json
import random
import sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\dopisannye-v4c.jsonl", encoding="utf-8")]
з = [x for x in {x["recipient_id"]: x for x in з if x.get("review_id")}.values()]
random.seed(29)
for x in random.sample(з, min(N, len(з))):
    print("=" * 70)
    print("%s | карточка %s\nПРИЧИНА: %s" % (x["имя"], x["review_id"], x["причина"]))
    if x["было_тема"] != x["тема"]:
        print("ТЕМА было: %s\nТЕМА стало: %s" % (x["было_тема"], x["тема"]))
    а, б = x["было"].split("\n\n"), x["тело"].split("\n\n")
    for оп, i1, i2, j1, j2 in difflib.SequenceMatcher(None, а, б).get_opcodes():
        if оп != "equal":
            print("--- было:\n" + "\n\n".join(а[i1:i2]))
            print("+++ стало:\n" + "\n\n".join(б[j1:j2]))
