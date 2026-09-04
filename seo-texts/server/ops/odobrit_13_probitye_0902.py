# -*- coding: utf-8 -*-
"""Одобрить письма партии 13, чьи адреса проба уже подтвердила.

Берём только вердикты «есть» и «принимает всё». Непроверенные, «неясно»
и «отказ пробе» остаются в pending до прогона пробы.

argv: проба | делать
"""
import datetime as dt
import hashlib
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store, MessageIn     # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
КАМПАНИЯ = 13
ГОДНЫЕ = ("есть", "принимает всё")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
print("время панели: %s" % сейчас.strftime("%Y-%m-%d %H:%M"))

вердикт = {}
for р in c.execute("SELECT LOWER(email) e, verdict FROM addr_probe"):
    вердикт[р["e"]] = р["verdict"]

обзоры = list(c.execute("SELECT id, recipient_id, email, message_id, status"
                        " FROM confirm_reviews WHERE campaign_id=? ORDER BY id",
                        (КАМПАНИЯ,)))
ждут = [р for р in обзоры if р["status"] == "pending"]
годные = [р for р in ждут if вердикт.get(str(р["email"]).lower()) in ГОДНЫЕ]
прочие = [р for р in ждут if р not in годные]
раскл = {}
for р in прочие:
    раскл[str(вердикт.get(str(р["email"]).lower()))] = \
        раскл.get(str(вердикт.get(str(р["email"]).lower())), 0) + 1
print("писем в кампании %d, ждут решения %d" % (len(обзоры), len(ждут)))
print("  годны к отправке сейчас: %d" % len(годные))
print("  остаются ждать пробы: %d %s" % (len(прочие), раскл))

if not ДЕЛАТЬ:
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

шаг = c.execute("SELECT id FROM sequence_steps WHERE campaign_id=?",
                (КАМПАНИЯ,)).fetchone()
if шаг is None:
    об = c.execute("SELECT * FROM sequence_steps WHERE campaign_id=11").fetchone()
    c.execute("INSERT INTO sequence_steps (campaign_id, step_index, delay_hours,"
              " subject_tmpl, body_tmpl, engagement_gate, include_legal, active,"
              " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (КАМПАНИЯ, об["step_index"], об["delay_hours"], об["subject_tmpl"],
               об["body_tmpl"], об["engagement_gate"], об["include_legal"], 1,
               сейчас.isoformat()))
    c.commit()
    шаг = c.execute("SELECT id FROM sequence_steps WHERE campaign_id=?",
                    (КАМПАНИЯ,)).fetchone()
    print("создан шаг последовательности id=%s" % шаг["id"])
шаг_ид = шаг["id"]

ст = {"письма": 0, "привязано": 0, "одобрено": 0, "ошибка": 0}
for р in годные:
    ключ = hashlib.sha256(("kasanie2|%d|%s|%s" % (КАМПАНИЯ, р["recipient_id"],
                                                  р["email"])).encode()).hexdigest()
    try:
        мид, новое = store.enqueue_message(
            MessageIn(idempotency_key=ключ, campaign_id=КАМПАНИЯ,
                      recipient_id=р["recipient_id"], sequence_step_id=шаг_ид,
                      scheduled_at=сейчас), status="pending_review")
        ст["письма"] += 1 if новое else 0
        store.confirm_set_message(р["id"], мид)
        ст["привязано"] += 1
        if store.confirm_decide(р["id"], status="approved", decided_by="владелец"):
            ст["одобрено"] += 1
    except Exception as ex:
        ст["ошибка"] += 1
        if ст["ошибка"] <= 3:
            print("  ошибка на %s: %s" % (р["email"], str(ex)[:120]))
print("\n=== СДЕЛАНО ===")
for k, v in ст.items():
    print("  %-12s %d" % (k, v))

print("\n=== ПРОВЕРКА ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=?"
                   " GROUP BY status", (КАМПАНИЯ,)):
    print("  письма %-16s %d" % (р["status"], р["k"]))
for р in c.execute("SELECT status, COUNT(*) k FROM confirm_reviews WHERE campaign_id=?"
                   " GROUP BY status", (КАМПАНИЯ,)):
    print("  решения %-16s %d" % (р["status"], р["k"]))
print("  с телом письма: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? AND"
                  " body_rendered<>''", (КАМПАНИЯ,)).fetchone()[0])
