# -*- coding: utf-8 -*-
"""Только чтение: сколько писем реально выйдет из группы meyer-v30.

Повторяет ДЕШЁВЫЕ отсечки прогона (ИНН+почта, дубль фирмы, уже писали,
исчерпал попытки, заслон confirm) и не трогает платные."""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.confirm import ConfirmSend    # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402

ИМЯ = "meyer-v30"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

сделано, попыток = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:
            continue
        i = str(z.get("inn") or "")
        if not i:
            continue
        попыток[i] += 1
        if z.get("ок"):
            сделано.add(i)

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ИМЯ in (gr or []))
счёт = Counter()
видели = set()
годных = 0
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if inn in видели:
        счёт["дубль строки той же фирмы"] += 1
        continue
    видели.add(inn)
    if inn in сделано:
        счёт["письмо уже есть"] += 1
        continue
    if попыток[inn] >= 3:
        счёт["исчерпал 3 попытки"] += 1
        continue
    п = cs._guard(inn=inn, email=email)
    if п:
        счёт["заслон: %s" % str(п).split(":")[0][:34]] += 1
        continue
    годных += 1

print("=== ГРУППА «%s» ===" % ИМЯ)
print("  строк в группе: %d" % len(в_группе))
print("\n=== ОТСЕЯНО ДЕШЁВЫМИ ОТСЕЧКАМИ ===")
for k, v in счёт.most_common():
    print("  %-40s %6d" % (k, v))

print("\n=== ИТОГ ===")
print("  КАНДИДАТОВ, ГОТОВЫХ К ГЕНЕРАЦИИ: %d" % годных)
print("  (это ДО платных отсечек: направление, предклассификатор, гейт покупателя)")
for о, п in (("осторожно 60%%", 0.60), ("по вчерашнему 73%%", 0.73), ("лучший случай 89%%", 0.89)):
    print("  писем при отдаче %-20s ~%d" % (о, int(годных * п)))
