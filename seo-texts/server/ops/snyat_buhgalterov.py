# -*- coding: utf-8 -*-
"""Снять из очереди письма на адреса чужих бухгалтерий.

Случай 25.08: письмо «Автобану» ушло на nalog-k@bk.ru, ответила «Налоговая
Консультация» — адрес из базы обзвона принадлежит конторе, которая сдаёт за
компанию отчётность. Владелец: «снять эти три».

Снимаем ровно перечисленные адреса, не по маске: buh@ на СОБСТВЕННОМ домене
компании — это её же бухгалтерия, туда писать нормально, и маска убила бы и
их. Заодно помечаем адрес в обогащении, чтобы он не вернулся новой партией.
"""
import io
import json
import os
import sqlite3
import sys
import time

АДРЕСА = ["buhonov@list.ru", "buh_group@mail.ru", "nalog@knopka.com",
          "nalog-k@bk.ru"]   # последний уже ушёл — метим, чтобы не вернулся
ПРИЧИНА = ("адрес чужой бухгалтерии/аутсорса, а не компании "
           "(владелец 25.08, случай nalog-k@bk.ru)")
ДЕЛАТЬ = "primenit" in sys.argv[1:]
ЖУРНАЛ = r"C:\sender\_ops\snyatye-buhgalterii.jsonl"

s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
s.row_factory = sqlite3.Row
места = ",".join("?" * len(АДРЕСА))
цель = s.execute(
    "SELECT m.id mid, m.status ms, cr.id cid, cr.status cs, r.id rid, "
    "       r.email, r.company_name, r.inn "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE LOWER(r.email) IN (%s) AND m.status IN ('scheduled','sending')"
    % места, [а.lower() for а in АДРЕСА]).fetchall()
print("=== ПИСЬМА В ОЧЕРЕДИ НА ЭТИ АДРЕСА: %d ===" % len(цель))
for р in цель:
    print("   письмо #%-6s %-22s %-34s ИНН %s"
          % (р["mid"], р["email"], str(р["company_name"] or "")[:34], р["inn"]))

# Есть ли у этих компаний другой адрес — тогда письмо не потеряно, его можно
# перецелить, а не выбрасывать насовсем.
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
print("\n=== ДРУГИЕ АДРЕСА ЭТИХ КОМПАНИЙ ===")
for р in цель:
    иные = [x["email"] for x in e.execute(
        "SELECT email FROM emails WHERE inn=? AND LOWER(email)<>?",
        (р["inn"], (р["email"] or "").lower()))]
    print("   %-34s %s" % (str(р["company_name"] or "")[:34],
                           ", ".join(иные) if иные else "других нет"))

if not ДЕЛАТЬ:
    print("\nвхолостую. Снять — primenit")
    raise SystemExit(0)

снято = []
for р in цель:
    s.execute("UPDATE messages SET status='skipped', last_error=?, "
              "       updated_at=datetime('now') WHERE id=?", (ПРИЧИНА, р["mid"]))
    if р["cid"] and р["cs"] not in ("sent",):
        s.execute("UPDATE confirm_reviews SET status='skipped', "
                  "       decided_by='чужая бухгалтерия (владелец 25.08)', "
                  "       decided_at=datetime('now'), reason=?, "
                  "       updated_at=datetime('now') WHERE id=?",
                  (ПРИЧИНА, р["cid"]))
    снято.append({"письмо": р["mid"], "адрес": р["email"],
                  "компания": р["company_name"], "инн": р["inn"]})
s.commit()

# Durable: и в журнал на сервере, и пометкой в обогащении, иначе адрес
# вернётся следующей же партией генерации.
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ф:
    for з in снято:
        ф.write(json.dumps({**з, "причина": ПРИЧИНА, "ts": time.time()},
                           ensure_ascii=False) + "\n")
    ф.flush()
    os.fsync(ф.fileno())
кол = [р[1] for р in e.execute("PRAGMA table_info(emails)")]
if "addr_class" in кол:
    e.execute("UPDATE emails SET addr_class='чужая-бухгалтерия', "
              "       updated_at=? WHERE LOWER(email) IN (%s)" % места,
              [time.strftime("%Y-%m-%dT%H:%M:%S")] + [а.lower() for а in АДРЕСА])
    e.commit()
    print("в обогащении помечено адресов: %d" % e.total_changes)
print("\nснято писем: %d" % len(снято))
print("очередь теперь: %d" % s.execute(
    "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending')"
    ).fetchone()[0])
