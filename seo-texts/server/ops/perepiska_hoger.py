# -*- coding: utf-8 -*-
"""Вся переписка с hoger.pro: что и когда мы туда отправляли.

Владелец 24.08: «в ответах есть письмо с "присылайте информацию на
info@hoger.pro" — мы туда отправляли что-то?».

По разбору дублей ИНН 7816693698 получил два письма в один день: на
vs@hoger.pro в 06:15 и на info@hoger.pro в 11:21. Вопрос в порядке
событий: если клиент попросил писать на info@ ПОСЛЕ того, как мы туда уже
написали, он получил одно и то же дважды и просьба звучит как «вы уже
писали не туда». Если ДО — мы просьбу выполнили.

Печатаем всё по домену разом: получателей, письма, события, лиды — в
одной шкале времени.
"""
import sqlite3

ДОМЕН = "hoger.pro"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ПОЛУЧАТЕЛИ ЭТОГО ДОМЕНА ===")
получатели = c.execute(
    "SELECT id, email, inn, company_name, mx_provider FROM recipients "
    " WHERE email LIKE ?", ("%@" + ДОМЕН,)).fetchall()
for р in получатели:
    print("  #%-6s %-26s ИНН %-13s mx=%-8s %s"
          % (р["id"], р["email"], р["inn"], str(р["mx_provider"] or "?"),
             str(р["company_name"] or "")[:34]))
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
    print("  %s  #%-6s %-14s -> %-24s | ящик %s"
          % (str(р["sent_at"] or р["created_at"])[:16], р["id"], р["status"],
             р["email"], str(р["mailbox_id"] or "?")[:32]))
    print("        %s" % str(р["subject"] or "")[:70])

print("\n=== СОБЫТИЯ В ОДНОЙ ШКАЛЕ ===")
for р in c.execute(
        "SELECT e.event_ts, e.event_type, e.mailbox_id, e.message_id, "
        "       r.email, e.detail_json FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.recipient_id IN (%s) ORDER BY e.event_ts" % места, ids):
    print("  %s  [%-11s] %-24s | письмо %s"
          % (str(р["event_ts"])[:19], р["event_type"], str(р["email"] or "?"),
             р["message_id"]))
    д = str(р["detail_json"] or "")
    и = д.find('"snippet"')
    if и >= 0:
        print("        %s" % д[и:и + 200].replace("\\n", " "))

print("\n=== ЛИДЫ ===")
кол = [с[1] for с in c.execute("PRAGMA table_info(leads)")]
поля = [п for п in ("id", "email", "recipient_id", "status", "reply_kind",
                    "phone", "created_at") if п in кол]
for р in c.execute("SELECT %s FROM leads WHERE email LIKE ? ORDER BY id"
                   % ", ".join(поля), ("%@" + ДОМЕН,)):
    print("  " + " | ".join("%s=%s" % (п, str(р[п])[:40]) for п in поля
                            if р[п] not in (None, "")))

print("\n=== ЧТО В ОЧЕРЕДИ СЕЙЧАС ===")
for р in c.execute(
        "SELECT id, status, kind, created_at, subject FROM confirm_reviews "
        " WHERE recipient_id IN (%s) ORDER BY id" % места, ids):
    print("  #%-6s %-12s %-10s %s | %s"
          % (р["id"], р["status"], str(р["kind"] or ""),
             str(р["created_at"])[:16], str(р["subject"] or "")[:46]))
