# -*- coding: utf-8 -*-
"""Забрать вердикты пробы у VPS и одобрить чистые письма партии 13.

Одобряем только «есть» и «принимает всё». «Неясно», «отказ пробе»,
«нет ящика», «нет MX» остаются в pending и не уходят.

argv: проба | делать
"""
import datetime as dt
import hashlib
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                # noqa: E402
from sender.store import Store, MessageIn       # noqa: E402
from sender.addr_probe import build_addr_probe  # noqa: E402
import sender.probe_sync as PS                  # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
КАМПАНИЯ, ГОДНЫЕ = 13, ("есть", "принимает всё")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

петля = build_addr_probe(store, cfg)
ps = PS.build_probe_sync(store, getattr(петля, "probe_", петля), cfg)
взято = ps.забрать()
print("забрано у работника: %s" % взято)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
вердикт = {str(р["e"]): р["verdict"] for р in c.execute(
    "SELECT LOWER(email) e, verdict FROM addr_probe")}
ждут = list(c.execute("SELECT id, recipient_id, email FROM confirm_reviews"
                      " WHERE campaign_id=? AND status='pending'", (КАМПАНИЯ,)))
раскл = {}
for р in ждут:
    раскл[str(вердикт.get(str(р["email"]).lower()))] = \
        раскл.get(str(вердикт.get(str(р["email"]).lower())), 0) + 1
годные = [р for р in ждут if вердикт.get(str(р["email"]).lower()) in ГОДНЫЕ]
print("ждут решения: %d %s" % (len(ждут), раскл))
print("годны к отправке: %d" % len(годные))

if not ДЕЛАТЬ or not годные:
    print("ничего не изменено" if not ДЕЛАТЬ else "одобрять пока нечего")
    raise SystemExit(0)

шаг = c.execute("SELECT id FROM sequence_steps WHERE campaign_id=?",
                (КАМПАНИЯ,)).fetchone()["id"]
сейчас = dt.datetime.now()
ст = {"одобрено": 0, "ошибка": 0}
for р in годные:
    ключ = hashlib.sha256(("kasanie2|%d|%s|%s" % (КАМПАНИЯ, р["recipient_id"],
                                                  р["email"])).encode()).hexdigest()
    try:
        мид, _ = store.enqueue_message(
            MessageIn(idempotency_key=ключ, campaign_id=КАМПАНИЯ,
                      recipient_id=р["recipient_id"], sequence_step_id=шаг,
                      scheduled_at=сейчас), status="pending_review")
        store.confirm_set_message(р["id"], мид)
        if store.confirm_decide(р["id"], status="approved", decided_by="владелец"):
            ст["одобрено"] += 1
    except Exception as ex:
        ст["ошибка"] += 1
        if ст["ошибка"] <= 3:
            print("  ошибка на %s: %s" % (р["email"], str(ex)[:110]))
print("\n=== СДЕЛАНО ===")
print("  одобрено %d, ошибок %d" % (ст["одобрено"], ст["ошибка"]))
for р in c.execute("SELECT status, COUNT(*) k FROM confirm_reviews"
                   " WHERE campaign_id=? GROUP BY status", (КАМПАНИЯ,)):
    print("  решения %-12s %d" % (р["status"], р["k"]))
