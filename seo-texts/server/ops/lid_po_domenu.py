# -*- coding: utf-8 -*-
"""Есть ли ответ этого домена в ленте лидов. Аргумент — домен.

Владелец 24.08 показал ответ info@chzok.ru «На данный момент не актуально»
и спросил: «этот есть в ленте лидов?». Печатаем всё по домену разом —
получателей, письма, события (в т.ч. reply/skip), лиды.
"""
import sqlite3
import sys

ДОМЕН = next((a for a in sys.argv[1:] if "." in a and not a.startswith("-")),
             "chzok.ru")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("домен: %s" % ДОМЕН)

print("\n=== ПОЛУЧАТЕЛИ ===")
_кол_r = [с[1] for с in c.execute("PRAGMA table_info(recipients)")]
_доп = [п for п in ("status", "state", "mx_provider") if п in _кол_r]
получатели = c.execute(
    "SELECT id, email, inn, company_name%s FROM recipients WHERE email LIKE ?"
    % ("".join(", " + п for п in _доп)), ("%@" + ДОМЕН,)).fetchall()
for р in получатели:
    print("  #%-6s %-28s ИНН %-13s %-34s %s"
          % (р["id"], р["email"], р["inn"],
             str(р["company_name"] or "")[:34],
             " ".join("%s=%s" % (п, р[п]) for п in _доп if р[п] not in (None, ""))))
ids = [р["id"] for р in получатели]
if not ids:
    print("  таких получателей нет")
    raise SystemExit(0)
места = ",".join("?" * len(ids))

print("\n=== ПИСЬМА ===")
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.created_at, m.mailbox_id, "
        "       m.subject, r.email FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.recipient_id IN (%s) ORDER BY COALESCE(m.sent_at, m.created_at)"
        % места, ids):
    print("  %s  #%-6s %-12s -> %-26s | ящик %s"
          % (str(р["sent_at"] or р["created_at"])[:16], р["id"], р["status"],
             р["email"], str(р["mailbox_id"] or "?")[:30]))
    print("        %s" % str(р["subject"] or "")[:70])

print("\n=== СОБЫТИЯ ===")
for р in c.execute(
        "SELECT e.event_ts, e.event_type, e.message_id, r.email, e.detail_json "
        "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.recipient_id IN (%s) ORDER BY e.event_ts" % места, ids):
    print("  %s  [%-11s] %-26s | письмо %s"
          % (str(р["event_ts"])[:19], р["event_type"], str(р["email"] or "?"),
             р["message_id"]))
    д = str(р["detail_json"] or "")
    for ключ in ('"snippet"', '"reason"', '"kind"'):
        и = д.find(ключ)
        if и >= 0:
            print("        %s" % д[и:и + 180].replace("\\n", " "))

print("\n=== ЛИДЫ ===")
кол = [с[1] for с in c.execute("PRAGMA table_info(leads)")]
поля = [п for п in ("id", "email", "recipient_id", "status", "reply_kind",
                    "phone", "company_name", "created_at", "v_bitrix",
                    "tags", "note") if п in кол]
строк = 0
for р in c.execute("SELECT %s FROM leads WHERE email LIKE ? ORDER BY id"
                   % ", ".join(поля), ("%@" + ДОМЕН,)):
    строк += 1
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:60]) for п in поля
                            if р[п] not in (None, "")))
if not строк:
    print("  ЛИДА НЕТ")

print("\n=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ ===")
for р in c.execute(
        "SELECT id, status, kind, created_at, subject FROM confirm_reviews "
        " WHERE recipient_id IN (%s) ORDER BY id" % места, ids):
    print("  #%-6s %-12s %-10s %s | %s"
          % (р["id"], р["status"], str(р["kind"] or ""),
             str(р["created_at"])[:16], str(р["subject"] or "")[:46]))

print("\n=== ЧТО ВООБЩЕ ПРИШЛО СЕГОДНЯ (reply/skip) ===")
for р in c.execute(
        "SELECT event_ts, event_type, recipient_id, message_id FROM events "
        " WHERE event_ts >= date('now') AND event_type IN ('reply','skip') "
        " ORDER BY event_ts"):
    print("  %s [%-6s] получатель=%s письмо=%s"
          % (str(р["event_ts"])[:19], р["event_type"], р["recipient_id"],
             р["message_id"]))
