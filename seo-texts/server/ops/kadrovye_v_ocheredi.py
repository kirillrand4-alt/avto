# -*- coding: utf-8 -*-
"""Кадровые и прочие служебные ящики, проскочившие в обе партии."""
import io
import json
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ЛИШНИЕ = {"resume", "rezume", "cv", "personal", "otdelkadrov", "kadrovik",
          "trud", "vakans", "vakansiya", "career", "careers", "recruit",
          "recruiting", "hrm", "hrd", "praktika", "student", "sekretariat"}
_ЦИФ = re.compile(r"\d+$")
ids = []
for файл in (r"C:\sender\_ops\vtorye-adresa.jsonl",
             r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(файл, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                ids.append(int(d["review"]))
    except FileNotFoundError:
        pass
print("карточек в обеих партиях: %d" % len(ids))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
нашли = []
for r in c.execute("SELECT id, status, email FROM confirm_reviews "
                   " WHERE id IN (%s) AND status IN ('pending','approved')" % зн, ids):
    л = _ЦИФ.sub("", str(r["email"] or "").split("@")[0].lower())
    if л in ЛИШНИЕ:
        нашли.append((int(r["id"]), r["status"], r["email"], л))
c.close()
print("кадровых/служебных в работе: %d" % len(нашли))
for i, s_, e, л in нашли[:12]:
    print("   rev %-6s %-9s %-34s (%s)" % (i, s_, str(e)[:34], л))
if not КАТИТЬ or not нашли:
    raise SystemExit(0)
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
итог = Counter()
for i, s_, e, л in нашли:
    try:
        if s_ == "pending":
            ок = cs.skip(i, reason="служебный ящик (%s@): не адресат" % л,
                         operator="сверка ящиков 28.08")
            итог["снято из очереди" if ок else "не снялось"] += 1
        else:
            # уже одобрено и в расписании — снимаем письмо, решение не трогаем
            row = store.confirm_get(i) or {}
            mid = row.get("message_id")
            if mid:
                store.mark_skipped_if_not_terminal(
                    int(mid), "служебный ящик (%s@): не адресат" % л)
                итог["письмо снято с расписания"] += 1
            else:
                итог["approved без письма"] += 1
    except Exception as ex:                                       # noqa: BLE001
        итог["ошибка: " + str(ex)[:40]] += 1
print("")
for к, n in итог.most_common():
    print("   %-36s %4d" % (к, n))
