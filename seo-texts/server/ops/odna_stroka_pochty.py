# -*- coding: utf-8 -*-
"""Строка ровно по marushkiiin@yandex.ru и все адреса «Ре-Фил» с источниками."""
import sqlite3

ПОЧТА = "marushkiiin@yandex.ru"
ИНН = "7842186599"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
c.row_factory = sqlite3.Row
поля = [r[1] for r in c.execute("PRAGMA table_info(emails)")]
свой = c.execute("SELECT * FROM emails WHERE email=?", (ПОЧТА,)).fetchone()
все = [dict(r) for r in c.execute(
    "SELECT * FROM emails WHERE inn=? ORDER BY email", (ИНН,))]
c.close()

print("=" * 82)
print("=== СВОДКА: ПЕРВОИСТОЧНИК %s ===" % ПОЧТА)
print("колонки таблицы emails: %s" % ", ".join(поля))
print("")
if свой:
    print("--- ЕГО СТРОКА ---")
    for к in свой.keys():
        if свой[к] not in (None, ""):
            print("   %-20s %s" % (к, str(свой[к])[:200]))
else:
    print("   строки по этому адресу в enrich.emails НЕТ")
print("")
print("--- ВСЕ АДРЕСА ООО «РЕ-ФИЛ» (%d) ---" % len(все))
for п in все:
    print("   %-32s источник %-16s роль %-10s %s"
          % (str(п.get("email"))[:32], str(п.get("source") or "—")[:16],
             str(п.get("role") or "—")[:10],
             str(п.get("url") or п.get("page") or "")[:40]))
