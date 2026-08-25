# -*- coding: utf-8 -*-
"""Все ли ответы клиентов дошли до ленты лидов.

Сверяем входящие события с карточками лидов. Ответ, не ставший лидом, —
это молча потерянный клиент: письмо в ящике есть, а менеджер его не увидит.
Смотрим и «other» тоже: 25.08 туда лёг живой автоответ «в отпуске до 30.08».
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
кол = [р[1] for р in c.execute("PRAGMA table_info(leads)")]
print("leads: %s" % ", ".join(кол))
кол_соб = [р[1] for р in c.execute("PRAGMA table_info(events)")]
print("events: %s\n" % ", ".join(кол_соб))
ЕСТЬ_ТРЕД = "thread_id" in кол_соб

print("=== ВХОДЯЩИЕ СОБЫТИЯ ПО ТИПАМ ===")
for р in c.execute("SELECT event_type, COUNT(*) n FROM events "
                   " GROUP BY event_type ORDER BY n DESC"):
    print("   %-16s %6d" % (р["event_type"], р["n"]))
всего_лидов = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
print("\nкарточек в ленте лидов: %d" % всего_лидов)

# У лида есть thread_id/recipient — по ним и сверяем.
лиды_по_треду = set()
лиды_по_получателю = set()
for р in c.execute("SELECT * FROM leads"):
    д = {к: р[к] for к in р.keys()}
    if д.get("thread_id"):
        лиды_по_треду.add(str(д["thread_id"]))
    if д.get("recipient_id"):
        лиды_по_получателю.add(int(д["recipient_id"]))
    for к in ("dedup_key",):
        if д.get(к):
            лиды_по_треду.add(str(д[к]))

print("\n=== ОТВЕТЫ КЛИЕНТОВ (event_type='reply') ===")
ответы = c.execute(
    "SELECT ев.id, ев.event_ts, ев.mailbox_id, ев.recipient_id, "
    "       %s тред, ев.detail_json, r.email, r.company_name "
    "  FROM events ев LEFT JOIN recipients r ON r.id=ев.recipient_id "
    " WHERE ев.event_type IN ('reply','reply_auto') ORDER BY ев.id DESC"
    % ("ев.thread_id" if ЕСТЬ_ТРЕД else "NULL")).fetchall()
print("всего ответов: %d" % len(ответы))
без_лида = []
for о in ответы:
    есть = ((о["тред"] and str(о["тред"]) in лиды_по_треду)
            or (о["recipient_id"] and int(о["recipient_id"]) in лиды_по_получателю))
    if not есть:
        без_лида.append(о)
print("без карточки в ленте: %d" % len(без_лида))
for о in без_лида[:15]:
    try:
        d = json.loads(о["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    print("   #%-7s %s %-30s %-28s %s"
          % (о["id"], str(о["event_ts"])[:16], str(о["email"] or "-")[:30],
             str(о["company_name"] or "-")[:28],
             str(d.get("snippet") or "").replace("\n", " ")[:44]))

print("\n=== «OTHER» С ПРИВЯЗКОЙ К ПОЛУЧАТЕЛЮ (могли быть ответами) ===")
прочие = c.execute(
    "SELECT ев.id, ев.event_ts, ев.recipient_id, ев.detail_json, r.email "
    "  FROM events ев JOIN recipients r ON r.id=ев.recipient_id "
    " WHERE ев.event_type='other' ORDER BY ев.id DESC LIMIT 40").fetchall()
подозрительные = 0
for о in прочие:
    try:
        d = json.loads(о["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    т = str(d.get("snippet") or d.get("body") or "").lower()
    if "dmarc" in т or "aggregate report" in т:
        continue
    подозрительные += 1
    в_ленте = int(о["recipient_id"]) in лиды_по_получателю
    if подозрительные <= 12:
        print("   #%-7s %s %-26s лид: %-3s %s"
              % (о["id"], str(о["event_ts"])[:16], str(о["email"] or "-")[:26],
                 "есть" if в_ленте else "НЕТ",
                 т.replace("\n", " ")[:46]))
print("   не-DMARC среди последних 40 «other»: %d" % подозрительные)
