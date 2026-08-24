# -*- coding: utf-8 -*-
"""Ответов сегодня 4, а видно 3 — где четвёртый.

Владелец 24.08 считает по панели 4 ответа, а глазами видит 3. Догадка:
счётчик складывает reply и reply_auto, а автоответ («в отпуске», «письмо
получено») — событие ответа, но не живой человек, и в ленте лидов ему
делать нечего.

Проверяем фактом: все события ответа за сегодня по отдельности, с кем,
с какого адреса и завёлся ли по нему лид. Если четвёртый — автоответ,
это видно сразу. Если живой, но лида нет — это уже поломка, и её надо
чинить.
"""
import sqlite3
import time

СЕГОДНЯ = time.strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ТАБЛИЦЫ = {р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}

print("=== СОБЫТИЯ ОТВЕТА ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT e.id, e.event_type, e.event_ts, e.recipient_id, e.mailbox_id, "
        "       e.detail_json, r.email, r.company_name, r.inn "
        "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type IN ('reply','reply_auto') "
        "   AND substr(e.event_ts,1,10)=? ORDER BY e.event_ts", (СЕГОДНЯ,)):
    print("\n  [%s] %s | пол.%s | ящик %s"
          % (р["event_type"], str(р["event_ts"])[:19], р["recipient_id"],
             str(р["mailbox_id"] or "?")[:34]))
    print("      компания: %s | ИНН %s | писали на %s"
          % (str(р["company_name"] or "?")[:40], р["inn"],
             str(р["email"] or "?")[:36]))
    if р["detail_json"]:
        print("      подробности: %s" % str(р["detail_json"])[:300])

print("\n=== СЧЁТ ПО ВИДАМ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT event_type, COUNT(*) n FROM events "
        " WHERE event_type IN ('reply','reply_auto','other') "
        "   AND substr(event_ts,1,10)=? GROUP BY event_type", (СЕГОДНЯ,)):
    print("  %-12s %d" % (р["event_type"], р["n"]))

print("\n=== ЛИДЫ ЗА СЕГОДНЯ ===")
if "leads" in ТАБЛИЦЫ:
    кол = [с[1] for с in c.execute("PRAGMA table_info(leads)")]
    поле_д = next((п for п in ("created_at", "ts", "updated_at") if п in кол),
                  None)
    поля = [п for п in ("id", "email", "recipient_id", "status", "reply_kind",
                        "phone", "dedup_key") if п in кол]
    if поле_д:
        поля_с = ", ".join(поля + [поле_д])
        for р in c.execute("SELECT %s FROM leads WHERE substr(%s,1,10)=? "
                           "ORDER BY id DESC" % (поля_с, поле_д), (СЕГОДНЯ,)):
            print("  " + " | ".join("%s=%s" % (п, str(р[п])[:34])
                                    for п in поля + [поле_д]
                                    if р[п] not in (None, "")))
        всего = c.execute("SELECT COUNT(*) FROM leads WHERE substr(%s,1,10)=?"
                          % поле_д, (СЕГОДНЯ,)).fetchone()[0]
        print("  ИТОГО лидов за сегодня: %d" % всего)
    else:
        print("  в leads нет поля даты, колонки: %s" % ", ".join(кол))
else:
    print("  таблицы leads нет; есть: %s"
          % ", ".join(sorted(т for т in ТАБЛИЦЫ if "lead" in т.lower()))
          or "  ни одной таблицы про лиды")

print("\n=== ВСЕ ЛИДЫ, ПОСЛЕДНИЕ 8 ===")
if "leads" in ТАБЛИЦЫ:
    кол = [с[1] for с in c.execute("PRAGMA table_info(leads)")]
    поля = [п for п in ("id", "email", "recipient_id", "status", "created_at")
            if п in кол]
    for р in c.execute("SELECT %s FROM leads ORDER BY id DESC LIMIT 8"
                       % ", ".join(поля)):
        print("  " + " | ".join("%s=%s" % (п, str(р[п])[:36]) for п in поля))
