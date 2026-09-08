# -*- coding: utf-8 -*-
"""В какой пул уйдёт каждое письмо партии - по mx_provider получателя."""
import json, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ТЕМА = "для качества: вопрос по сортировке зерна"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
маршрут = dict(cfg.get("provider_split.routing", {}) or {})
пулы = dict(cfg.provider_pools() or {})
напр = {str(getattr(mb, "mailbox_id", "")): str(getattr(mb, "division", "") or "?")
        for mb in cfg.mailboxes()}

пров = Counter()
в_пул = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT r.mx_provider FROM confirm_reviews c
                 JOIN recipients r ON c.recipient_id = r.id
                WHERE c.subject=? AND c.status='pending'""", (ТЕМА,)):
        p = str(р["mx_provider"] or "unknown").lower()
        пров[p] += 1
        пул = маршрут.get(p) or маршрут.get("other") or "?"
        в_пул[пул] += 1

print("--- провайдер получателя ---")
for к, в in пров.most_common(8):
    print("   %-16s %5d  → пул %s" % (к, в, маршрут.get(к) or маршрут.get("other")))
print("")
print("=" * 74)
print("=== КУДА ПОЙДЁТ ПАРТИЯ ===")
for к, в in в_пул.most_common():
    сп = пулы.get(к, [])
    м = sum(1 for x in сп if напр.get(str(x)) == "meyer")
    print("   пул %-14s писем %5d | ящиков %2d, Meyer из них %2d%s"
          % (к, в, len(сп), м, "  ← НЕТ MEYER, только через перелив" if not м else ""))
print("перелив включён: %s" % cfg.get("provider_split.overflow", False))
