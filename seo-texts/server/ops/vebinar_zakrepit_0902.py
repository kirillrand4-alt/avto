# -*- coding: utf-8 -*-
"""Закрепить письма, написанные от имени Ирины, за её ящиком.

Нужно потому, что ящик в письме выбирается ротацией в момент отправки, а в
44 письмах кампании 12 имя Ирины стоит прямо в тексте: уйти с чужого ящика
такое письмо не должно. Колонка messages.mailbox_id как раз для этого:
claim_due_messages берёт письмо, если mailbox_id пуст ИЛИ совпал с ящиком.

Запускать после одобрения писем в панели: до одобрения писем ещё нет.
argv: проба | делать
"""
import json
import sqlite3
import sys

ЯЩИК = "i.kuznetsova@sort-systems.ru"
КАМПАНИЯ = 12
ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

нужно = []
for р in c.execute("SELECT id, message_id, email, panel_json FROM confirm_reviews"
                   " WHERE campaign_id=? AND message_id IS NOT NULL", (КАМПАНИЯ,)):
    try:
        п = json.loads(р["panel_json"] or "{}")
    except Exception:
        continue
    if (п.get("vebinar") or {}).get("yashchik") == ЯЩИК:
        нужно.append((р["message_id"], р["email"]))

print("одобренных писем от имени Ирины: %d" % len(нужно))
if not нужно:
    print("закреплять нечего: письма ещё не одобрены")
    raise SystemExit(0)

ид = [m for m, _ in нужно]
впис = ",".join("?" * len(ид))
уже = c.execute("SELECT COUNT(*) FROM messages WHERE id IN (%s)"
                " AND mailbox_id=?" % впис, ид + [ЯЩИК]).fetchone()[0]
ушло = c.execute("SELECT COUNT(*) FROM messages WHERE id IN (%s)"
                 " AND status='sent'" % впис, ид).fetchone()[0]
print("  уже закреплено: %d, уже отправлено: %d" % (уже, ушло))

if not ДЕЛАТЬ:
    print("  будет закреплено: %d (режим пробы, ничего не изменено)"
          % (len(ид) - уже - ушло))
    raise SystemExit(0)

cur = c.execute("UPDATE messages SET mailbox_id=?, updated_at=datetime('now')"
                " WHERE id IN (%s) AND status IN ('scheduled','pending_review')"
                " AND (mailbox_id IS NULL OR mailbox_id='')" % впис, [ЯЩИК] + ид)
c.commit()
print("  закреплено сейчас: %d" % cur.rowcount)
print("  всего за ящиком Ирины: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE id IN (%s) AND mailbox_id=?"
                  % впис, ид + [ЯЩИК]).fetchone()[0])
