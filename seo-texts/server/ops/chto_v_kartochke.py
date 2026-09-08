# -*- coding: utf-8 -*-
"""Что реально лежит в карточке и в письме по одной компании."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ИСКАТЬ = "Попова"
store = Store(r"C:\sender\sender.db")
with store._lock:
    строки = store._conn.execute(
        "SELECT id, status, message_id, recipient_id, email, subject, body, "
        "       updated_at FROM confirm_reviews WHERE body LIKE ?",
        ("%" + ИСКАТЬ + "%",)).fetchall()
    print("карточек с «%s» в теле: %d" % (ИСКАТЬ, len(строки)))
    кол = [r[1] for r in store._conn.execute("PRAGMA table_info(messages)")]
    print("колонки messages: %s" % ", ".join(кол))
    for р in строки[:4]:
        т = str(р["body"] or "")
        новый = "решето и аспирация" in т
        print("")
        print("=" * 70)
        print("карточка %s | %s | %s | обновлена %s"
              % (р["id"], р["status"], р["email"], р["updated_at"]))
        print("ТЕКСТ КАРТОЧКИ: %s" % ("НОВЫЙ" if новый else "СТАРЫЙ"))
        print(т[:200])
        if р["message_id"]:
            поля = [c for c in ("id", "status", "subject", "updated_at")
                    if c in кол] + [c for c in кол
                                    if c in ("body_text", "body_html",
                                             "rendered_body", "text")]
            м = store._conn.execute(
                "SELECT %s FROM messages WHERE id=?" % ", ".join(поля),
                (int(р["message_id"]),)).fetchone()
            if м is None:
                print("письма нет")
            else:
                тм = ""
                for c in поля:
                    if c not in ("id", "status", "subject", "updated_at"):
                        тм = str(м[c] or "") or тм
                print("")
                print("ПИСЬМО %s | %s | обновлено %s | ТЕКСТ: %s"
                      % (м["id"], м["status"],
                         м["updated_at"] if "updated_at" in поля else "?",
                         "НОВЫЙ" if "решето и аспирация" in тм
                         else ("СТАРЫЙ" if тм.strip() else "ПУСТО")))
                print(тм[:200])
