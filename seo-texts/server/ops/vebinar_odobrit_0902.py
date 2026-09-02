# -*- coding: utf-8 -*-
"""Одобрение 175 писем кампании 12 и закрепление ящика Ирины.

Порядок важен и выбран так, чтобы ни одно письмо не могло уйти не с того
ящика: письма сначала заводятся в статусе pending_review (claim_due их не
берёт), потом закрепляется ящик у писем от имени Ирины, и только последним
шагом решение оператора переводит их в scheduled.

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

КАМПАНИЯ = 12
ЯЩИК_ИРИНЫ = "i.kuznetsova@sort-systems.ru"
ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

# --- шаг последовательности ---
шаг = c.execute("SELECT id FROM sequence_steps WHERE campaign_id=?",
                (КАМПАНИЯ,)).fetchone()
if шаг is None:
    образец = c.execute("SELECT * FROM sequence_steps WHERE campaign_id=11").fetchone()
    print("шага последовательности у кампании %d нет, будет создан по образцу 11-й"
          % КАМПАНИЯ)
    if ДЕЛАТЬ:
        c.execute("INSERT INTO sequence_steps (campaign_id, step_index, delay_hours,"
                  " subject_tmpl, body_tmpl, engagement_gate, include_legal, active,"
                  " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                  (КАМПАНИЯ, образец["step_index"], образец["delay_hours"],
                   образец["subject_tmpl"], образец["body_tmpl"],
                   образец["engagement_gate"], образец["include_legal"], 1,
                   dt.datetime.now().isoformat()))
        c.commit()
        шаг = c.execute("SELECT id FROM sequence_steps WHERE campaign_id=?",
                        (КАМПАНИЯ,)).fetchone()
        print("  создан шаг id=%s" % шаг["id"])
else:
    print("шаг последовательности: id=%s" % шаг["id"])
шаг_ид = шаг["id"] if шаг else None

обзоры = list(c.execute(
    "SELECT id, recipient_id, email, message_id, status, panel_json"
    " FROM confirm_reviews WHERE campaign_id=? ORDER BY id", (КАМПАНИЯ,)))
ждут = [р for р in обзоры if р["status"] == "pending"]
ирина = [р for р in ждут if (json.loads(р["panel_json"] or "{}").get("vebinar")
                             or {}).get("yashchik") == ЯЩИК_ИРИНЫ]
print("писем всего %d, ждут решения %d, из них от имени Ирины %d"
      % (len(обзоры), len(ждут), len(ирина)))

if not ДЕЛАТЬ:
    print("\n=== ЧТО БУДЕТ СДЕЛАНО ===")
    print("  1) завести %d писем в статусе pending_review" % len(ждут))
    print("  2) закрепить %d писем за ящиком %s" % (len(ирина), ЯЩИК_ИРИНЫ))
    print("  3) одобрить все %d: письма перейдут в scheduled" % len(ждут))
    print("  темп отправки: %s" % str(dict(cfg.get("send_pacing", {})))[:90])
    print("  ничего не изменено (режим пробы)")
    raise SystemExit(0)

сейчас = dt.datetime.now()
ст = {"письма": 0, "было": 0, "привязано": 0, "ошибка": 0}
для_пина = []
for р in ждут:
    ключ = hashlib.sha256(("vebinar|%d|%s|%s" % (КАМПАНИЯ, р["recipient_id"],
                                                 р["email"])).encode()).hexdigest()
    try:
        мид, новое = store.enqueue_message(
            MessageIn(idempotency_key=ключ, campaign_id=КАМПАНИЯ,
                      recipient_id=р["recipient_id"], sequence_step_id=шаг_ид,
                      scheduled_at=сейчас),
            status="pending_review")
        ст["письма" if новое else "было"] += 1
        store.confirm_set_message(р["id"], мид)
        ст["привязано"] += 1
        if р in ирина:
            для_пина.append(мид)
    except Exception as ex:
        ст["ошибка"] += 1
        if ст["ошибка"] <= 3:
            print("  ошибка на review %s: %s" % (р["id"], str(ex)[:130]))
print("заведено писем: новых %d, уже было %d, привязано к решениям %d, ошибок %d"
      % (ст["письма"], ст["было"], ст["привязано"], ст["ошибка"]))

# --- закрепление ящика ДО одобрения: в pending_review письмо не забирается ---
if для_пина:
    впис = ",".join("?" * len(для_пина))
    cur = c.execute("UPDATE messages SET mailbox_id=?, updated_at=?"
                    " WHERE id IN (%s) AND status='pending_review'" % впис,
                    [ЯЩИК_ИРИНЫ, dt.datetime.now().isoformat()] + для_пина)
    c.commit()
    print("закреплено за ящиком Ирины: %d из %d" % (cur.rowcount, len(для_пина)))

# --- одобрение ---
од = {"да": 0, "нет": 0}
for р in ждут:
    try:
        од["да" if store.confirm_decide(р["id"], status="approved",
                                        decided_by="владелец") else "нет"] += 1
    except Exception as ex:
        од["нет"] += 1
        if од["нет"] <= 3:
            print("  ошибка одобрения review %s: %s" % (р["id"], str(ex)[:130]))
print("одобрено: %d, не удалось: %d" % (од["да"], од["нет"]))

print("\n=== ПРОВЕРКА ПОСЛЕ ===")
for x in c.execute("SELECT status, COUNT(*) n FROM messages WHERE campaign_id=?"
                   " GROUP BY status", (КАМПАНИЯ,)):
    print("  письма %-16s %4d" % (x["status"], x["n"]))
print("  с телом письма: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? AND"
                  " body_rendered IS NOT NULL AND body_rendered<>''",
                  (КАМПАНИЯ,)).fetchone()[0])
print("  закреплено за Ириной: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? AND mailbox_id=?",
                  (КАМПАНИЯ, ЯЩИК_ИРИНЫ)).fetchone()[0])
пусто = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? AND"
                  " (mailbox_id IS NULL OR mailbox_id='')", (КАМПАНИЯ,)).fetchone()[0]
print("  в общей ротации (ящик не закреплён): %d" % пусто)
плохо = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=? AND"
                  " body_rendered LIKE '%Ирина Кузнецова%' AND"
                  " (mailbox_id IS NULL OR mailbox_id<>?)",
                  (КАМПАНИЯ, ЯЩИК_ИРИНЫ)).fetchone()[0]
print("  ОПАСНЫХ (текст от Ирины, ящик чужой или пустой): %d" % плохо)
