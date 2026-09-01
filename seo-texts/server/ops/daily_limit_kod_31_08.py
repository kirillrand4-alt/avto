# -*- coding: utf-8 -*-
"""Только чтение: _daily_limit целиком + домены новых и старых ящиков."""
import io
import re
import sys
from collections import Counter

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = None
for i, x in enumerate(стр):
    if re.match(r"\s*def _daily_limit", x):
        н = i
        break
print("=== sender.py: _daily_limit ===")
if н is not None:
    for i in range(н, min(н + 62, len(стр))):
        print("  %4d  %s" % (i + 1, стр[i][:112]))

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
НОВЫЕ = ("food-sort.ru", "sorting-systems", "rentgen-control", "optical-sort",
         "rentgen-inspec", "inspection-syst")
дом_с, дом_н = Counter(), Counter()
пул_с, пул_н = Counter(), Counter()
for mb in cfg.mailboxes():
    mid = mb.mailbox_id
    д = mid.split("@")[-1]
    нов = any(x in mid for x in НОВЫЕ)
    (дом_н if нов else дом_с)[д] += 1
    (пул_н if нов else пул_с)[str(getattr(mb, "pool", ""))] += 1

print("\n=== ИТОГ: ДОМЕНЫ ===")
print("  СТАРЫЕ (%d ящиков на %d доменах):" % (sum(дом_с.values()), len(дом_с)))
for д, n in дом_с.most_common():
    print("     %-34s %d" % (д, n))
print("  НОВЫЕ (%d ящиков на %d доменах):" % (sum(дом_н.values()), len(дом_н)))
for д, n in дом_н.most_common():
    print("     %-34s %d" % (д, n))
print("  пулы: старые %s | новые %s" % (dict(пул_с), dict(пул_н)))
