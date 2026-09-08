# -*- coding: utf-8 -*-
"""Только чтение: кому писал Цейзер на cryo-gas.ru и работает ли классификатор."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ПОЛУЧАТЕЛИ НА ДОМЕНЕ cryo-gas.ru ===")
for р in c.execute("SELECT id, email, company_name, inn, segment FROM recipients"
                   " WHERE domain='cryo-gas.ru' OR email LIKE '%cryo-gas.ru'"):
    print("  rid=%s %-28s %s | ИНН %s | %s"
          % (р["id"], р["email"], str(р["company_name"])[:34], р["inn"],
             р["segment"]))

print("\n=== ПИСЬМА С ЯЩИКА o.tseyzer@kompressor-expert.ru НА ЭТОТ ДОМЕН ===")
for р in c.execute(
        "SELECT m.id, m.recipient_id, m.campaign_id, m.status, m.sent_at,"
        " m.subject, r.email FROM messages m JOIN recipients r"
        " ON r.id=m.recipient_id WHERE m.mailbox_id='o.tseyzer@kompressor-expert.ru'"
        " AND (r.domain='cryo-gas.ru' OR r.email LIKE '%cryo-gas.ru')"
        " ORDER BY m.sent_at"):
    print("  msg=%s rid=%s камп=%s %s %s | %s -> %s"
          % (р["id"], р["recipient_id"], р["campaign_id"], р["status"],
             str(р["sent_at"])[:19], str(р["subject"])[:40], р["email"]))

print("\n=== ВСЕ ПИСЬМА НА ЭТОТ ДОМЕН ===")
for р in c.execute(
        "SELECT m.id, m.recipient_id, m.campaign_id, m.status, m.sent_at,"
        " m.mailbox_id, m.subject, r.email FROM messages m JOIN recipients r"
        " ON r.id=m.recipient_id WHERE r.domain='cryo-gas.ru'"
        " OR r.email LIKE '%cryo-gas.ru' ORDER BY m.sent_at"):
    print("  msg=%s rid=%s камп=%s %-7s %s ящик=%s -> %s"
          % (р["id"], р["recipient_id"], р["campaign_id"], р["status"],
             str(р["sent_at"])[:19], str(р["mailbox_id"])[:34], р["email"]))
c.close()

print("\n=== ПРОВЕРКА КЛАССИФИКАТОРА НА ЗАВЕДОМЫХ ТЕКСТАХ ===")
try:
    from sender.reply_classify import classify_reply
    примеры = [
        ("Re: тест", "Спасибо, но нам это не интересно, предложение не актуально."),
        ("Re: тест", "Планов по замене или модернизации у нашей организации нет."),
        ("Re: тест", "Вопрос для нас актуален и интересен"),
        ("Re: тест", "Пришлите пожалуйста коммерческое предложение и цены."),
        ("Автоответ", "Я нахожусь в отпуске до 10 сентября."),
        ("Re: тест", "Отпишите нас от рассылки."),
    ]
    for тема, текст in примеры:
        с = classify_reply(тема, текст, {})
        print("  %-14s <- %s" % (getattr(с, "kind", "?"), текст[:62]))
except Exception as ex:                                          # noqa: BLE001
    print("  ошибка:", ex)
