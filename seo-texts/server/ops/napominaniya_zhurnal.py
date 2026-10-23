# -*- coding: utf-8 -*-
"""Первые N заведённых напоминаний из журнала пилота: napominaniya_zhurnal.py [N=20] [с=0]"""
import io
import json
import sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
С = int(sys.argv[2]) if len(sys.argv) > 2 else 0
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
print("в журнале:", len(з), "pending:", sum(1 for x in з if x.get("status") == "pending"))
for x in з[С:С + N]:
    print("=" * 60)
    print("#%s %s | заход %s | %s | %s" % (x.get("karta"), x.get("status"), x["zahod"], x["email"], x["mailbox"]))
    print(x["telo"])
