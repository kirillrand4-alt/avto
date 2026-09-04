# -*- coding: utf-8 -*-
"""Только чтение: что копировать во второе письмо и знаем ли имя адресата."""
import re
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

print("=== ИСХОДНОЕ ПИСЬМО: РЕШЕНИЕ ПРОТИВ ОТПРАВЛЕННОГО ===")
р = s.execute("SELECT cr.body реш, m.body_rendered ушло, cr.subject, r.email, r.inn"
              " FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id"
              " JOIN recipients r ON r.id=m.recipient_id"
              " WHERE m.status='sent' AND m.campaign_id=11"
              " AND cr.body LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%' LIMIT 1").fetchone()
if р:
    print("  адресат: %s" % р["email"])
    print("  --- в решении (что копируем) ---")
    print("  " + "\n  ".join(str(р["реш"]).splitlines()[:4]))
    print("  --- что реально ушло ---")
    print("  " + "\n  ".join(str(р["ушло"]).splitlines()[:4]))

print("\n=== СКОЛЬКО РЕШЕНИЙ ХРАНЯТ МЕТКУ ===")
n1 = s.execute("SELECT COUNT(*) FROM confirm_reviews WHERE body LIKE"
               " '%ИМЯ_ОТПРАВИТЕЛЯ%'").fetchone()[0]
n2 = s.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status IN"
               " ('approved','edited','sent')").fetchone()[0]
print("  с меткой ИМЯ_ОТПРАВИТЕЛЯ: %d из %d решённых" % (n1, n2))

print("\n=== КАК НАЧИНАЮТСЯ ПИСЬМА (первая строка) ===")
вид = {}
for р2 in s.execute("SELECT body FROM confirm_reviews WHERE status IN"
                    " ('approved','edited','sent') AND body<>'' LIMIT 4000"):
    п = str(р2["body"]).strip().splitlines()[0] if р2["body"] else ""
    if re.match(r"^[А-ЯЁ][а-яё]+( [А-ЯЁ][а-яё]+)?, (добрый день|здравствуйте)", п, re.I):
        к = "по имени"
    elif re.match(r"^(добрый день|здравствуйте)", п, re.I):
        к = "без имени"
    else:
        к = "другое: " + п[:40]
    вид[к] = вид.get(к, 0) + 1
for к, v in sorted(вид.items(), key=lambda x: -x[1])[:6]:
    print("  %-40s %d" % (к[:40], v))

print("\n=== ЗНАЕМ ЛИ ИМЯ ПО НОВЫМ АДРЕСАМ ===")
кол = [r["name"] for r in e.execute("PRAGMA table_info(emails)")]
print("  поля про человека: %s"
      % ", ".join(k for k in кол if k in ("person", "imya_ok", "role", "zahod_fio",
                                          "zahod_rol", "rol_istochnik", "addr_class")))
for р3 in e.execute("SELECT person, COUNT(*) n FROM emails WHERE source='own-site'"
                    " GROUP BY (person IS NULL OR person='') ORDER BY n DESC"):
    print("  person заполнен: %s -> %d"
          % ("нет" if not р3["person"] else "да", р3["n"]))
for р4 in e.execute("SELECT person, email FROM emails WHERE source='own-site'"
                    " AND person IS NOT NULL AND person<>'' LIMIT 5"):
    print("    %-34s %s" % (р4["email"][:34], р4["person"]))
