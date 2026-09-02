# -*- coding: utf-8 -*-
"""Только чтение: сходится ли закреплённый ящик с текстом письма."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
Я = "i.kuznetsova@sort-systems.ru"

всего = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0]
пин = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND mailbox_id=?",
                (Я,)).fetchone()[0]
имя_в_теле = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                       " body_rendered LIKE '%Ирина Кузнецова%'").fetchone()[0]
метка = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                  " body_rendered LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'").fetchone()[0]
print("писем %d | закреплено за Ириной %d | с её именем в тексте %d | с меткой %d"
      % (всего, пин, имя_в_теле, метка))

плохо1 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                   " body_rendered LIKE '%Ирина Кузнецова%' AND"
                   " (mailbox_id IS NULL OR mailbox_id<>?)", (Я,)).fetchone()[0]
плохо2 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                   " mailbox_id=? AND body_rendered NOT LIKE '%Ирина Кузнецова%'",
                   (Я,)).fetchone()[0]
print("  имя Ирины в тексте, а ящик чужой/пустой: %d" % плохо1)
print("  ящик Ирины закреплён, а текст общий: %d" % плохо2)

print("\n=== ПРИМЕРЫ РАСХОЖДЕНИЯ ===")
for р in c.execute("SELECT id, email, mailbox_id, substr(body_rendered,1,90) t"
                   " FROM messages WHERE campaign_id=12 AND mailbox_id=?"
                   " AND body_rendered NOT LIKE '%Ирина Кузнецова%' LIMIT 4", (Я,)):
    print("  msg#%s %s -> %s" % (р["id"], р["email"], р["t"].replace("\n", " ")[:70]))
for р in c.execute("SELECT id, email, mailbox_id, substr(body_rendered,1,90) t"
                   " FROM messages WHERE campaign_id=12 AND"
                   " body_rendered LIKE '%Ирина Кузнецова%' AND"
                   " (mailbox_id IS NULL OR mailbox_id<>?) LIMIT 4", (Я,)):
    print("  msg#%s %s ящик=%s -> %s"
          % (р["id"], р["email"], р["mailbox_id"], р["t"].replace("\n", " ")[:60]))
