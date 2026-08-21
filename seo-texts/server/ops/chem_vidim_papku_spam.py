# -*- coding: utf-8 -*-
"""Чем МЫ сейчас можем узнать, куда легло письмо: в «Входящие» или в «Спам».

Вопрос владельца: видно ли это по коду ответа SMTP. Прежде чем отвечать,
смотрим, что вообще есть в системе: типы событий, включён ли трекинг
открытий, ловим ли жалобы (FBL), и есть ли у нас свои адреса-маяки, по
которым можно проверить попадание глазами.
"""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("события в журнале:")
for р in c.execute("SELECT event_type, COUNT(*) n FROM events "
                   "GROUP BY event_type ORDER BY n DESC"):
    print(f"  {р['n']:>6}  {р['event_type']}")

cfg = Config.load(r"C:\sender\sender.yaml")
for ключ in ("tracking.open_pixel", "tracking.enabled", "tracking.base_url",
             "unsub_server.base_url", "fbl.enabled", "postmaster.enabled"):
    try:
        print(f"{ключ}: {cfg.get(ключ, '(нет ключа)')}")
    except Exception as ex:                                        # noqa: BLE001
        print(f"{ключ}: ошибка {str(ex)[:40]}")

# храним ли ответ сервера на УСПЕШНУЮ отправку
колонки = [р[1] for р in c.execute("PRAGMA table_info(messages)")]
print(f"\nколонки messages: {', '.join(колонки)}")
print("ответ почтовика на успех храним:",
      "да" if any(k in колонки for k in ("smtp_response", "accept_response"))
      else "НЕТ - только ошибки в last_error")

# свои адреса среди получателей: маяки
свои = [р["email"] for р in c.execute(
    "SELECT DISTINCT email FROM recipients WHERE email LIKE '%@mail.ru' "
    "   OR email LIKE '%@yandex.ru' LIMIT 5")]
наши_домены = {mb.mailbox_id.split("@")[-1] for mb in cfg.mailboxes()}
маяки = [р["email"] for р in c.execute("SELECT DISTINCT email FROM recipients")
         if str(р["email"] or "").split("@")[-1] in наши_домены]
print(f"\nадресов-маяков (наши домены среди получателей): {len(маяки)}")
print("ящиков панели (можно читать по IMAP):", len(наши_домены), "доменов,",
      len(list(cfg.mailboxes())), "ящиков")
