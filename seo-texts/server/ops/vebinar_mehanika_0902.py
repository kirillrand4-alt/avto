# -*- coding: utf-8 -*-
"""Только чтение: как ставить письма в очередь и что их держит до подтверждения."""
import inspect
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender import store as S  # noqa: E402

print("=== MessageIn / RecipientIn / CampaignIn ===")
for имя in ("MessageIn", "RecipientIn", "CampaignIn", "SuppressionIn"):
    к = getattr(S, имя, None)
    if к is None:
        try:
            import sender.models as M
            к = getattr(M, имя, None)
        except Exception:
            к = None
    if к is not None:
        поля = getattr(к, "__dataclass_fields__", None) or getattr(к, "model_fields", None)
        if поля:
            print("  %s: %s" % (имя, ", ".join(поля.keys())))
        else:
            print("  %s: %s" % (имя, str(inspect.signature(к))[:300]))

print("\n=== claim_due_messages: код ===")
try:
    print(inspect.getsource(S.Store.claim_due_messages)[:1400])
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:120])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== СТАТУСЫ messages ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages GROUP BY status ORDER BY n DESC"):
    print("  %-14s %6d" % (р["status"], р["n"]))

print("\n=== confirm_reviews ===")
try:
    кк = [r["name"] for r in c.execute("PRAGMA table_info(confirm_reviews)")]
    print("  колонки: %s" % ", ".join(кк))
    for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews GROUP BY status"):
        print("  %-14s %6d" % (р["status"], р["n"]))
    об = c.execute("SELECT * FROM confirm_reviews ORDER BY id DESC LIMIT 1").fetchone()
    if об:
        print("  последняя: " + " | ".join("%s=%s" % (k, str(об[k])[:40]) for k in кк))
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:150])

print("\n=== ИТОГ ===")
print("  выше: поля MessageIn, условие выборки к отправке, статусы и очередь подтверждений")
