# -*- coding: utf-8 -*-
"""N случайных заведённых напоминаний из журнала (только чтение).
    napominaniya_sluchaynye.py [N=10] [журнал=napominaniya-v2]"""
import io, json, random, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ж = sys.argv[2] if len(sys.argv) > 2 else "napominaniya-v2"
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\%s.jsonl" % ж, encoding="utf-8")]
з = [x for x in з if x.get("status") == "pending"]
print("заведено pending:", len(з))
for x in random.sample(з, min(N, len(з))):
    print("=" * 60)
    print("шаблон %s | %s | %s | от %s" % (x["zahod"], x["email"], x["tema"], x["mailbox"]))
    print(x["telo"])
