# -*- coding: utf-8 -*-
"""Снять из очереди подтверждения (владелец 14.10: «сними эти 7»): письма на
удержании, где компания нам отвечала, где повтор адресу правилом не разрешён,
и с мёртвым MX. Штатно: store.confirm_decide(status='skipped') — карточка и
письмо в одной транзакции.

    snyat_7_iz_ocheredi.py [--primenit]
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
снять = []
for р in c.execute("SELECT id, inn, email, panel_json FROM confirm_reviews WHERE status='pending'"):
    try:
        п = json.loads(р["panel_json"] or "{}")
    except Exception:  # noqa: BLE001
        continue
    if not (п.get("actions") or {}).get("confirm_hold"):
        continue
    коды = {f.get("code") for f in (п.get("stop_flags") or [])}
    if "mx_dead" in коды:
        снять.append((р["id"], р["email"], "мёртвый MX"))
    elif коды == {"recent_contact"}:
        if cs._otvechali(р["inn"]):
            снять.append((р["id"], р["email"], "компания нам отвечала"))
        elif cs._recent_contact(email=р["email"]) is not None:
            снять.append((р["id"], р["email"], "адрес писали < 90 дн, повтор не разрешён"))
print("к снятию: %d; %s" % (len(снять), dict(Counter(x[2] for x in снять))))
for rid, em, поч in снять:
    print("   #%s %s — %s" % (rid, em, поч))
if ПРИМ:
    n = 0
    for rid, _em, поч in снять:
        n += bool(store.confirm_decide(rid, status="skipped", reason="снято 14.10 по слову владельца: " + поч,
                                       decided_by="claude-ops"))
    print("снято: %d" % n)
print("=== СНЯТЬ 7: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
