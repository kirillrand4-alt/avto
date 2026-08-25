# -*- coding: utf-8 -*-
"""Почему ответ оператора не виден в самом почтовом ящике.

Гипотеза из кода: панель шлёт ответ по SMTP, а копию в папку
«Отправленные» никто не кладёт — IMAP APPEND в проекте не зовётся нигде.
SMTP доставляет письмо получателю, но своей копии у отправителя не
оставляет: её кладёт веб-интерфейс почтовика, когда пишешь оттуда.

Проверяем живьём: берём ящик, которым недавно отвечали, смотрим его папки
и сколько писем лежит в «Отправленных» против наших отправок за тот же
день по базе.
"""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== ПОСЛЕДНИЕ ОТВЕТЫ ОПЕРАТОРА (события reply_sent) ===")
ответы = c.execute(
    "SELECT id, event_ts, mailbox_id, recipient_id FROM events "
    " WHERE event_type='reply_sent' ORDER BY id DESC LIMIT 6").fetchall()
for р in ответы:
    есть = c.execute(
        "SELECT COUNT(*) FROM messages WHERE recipient_id=? "
        "   AND substr(COALESCE(sent_at,''),1,10)=substr(?,1,10)",
        (р["recipient_id"], р["event_ts"])).fetchone()[0]
    print("   #%-7s %s %-38s строк в messages за тот день: %d"
          % (р["id"], str(р["event_ts"])[:19], р["mailbox_id"], есть))

if not ответы:
    raise SystemExit("ответов не было — сверять нечего")
ящик = ответы[0]["mailbox_id"]
день = str(ответы[0]["event_ts"])[:10]
наших = c.execute("SELECT COUNT(*) FROM messages WHERE mailbox_id=? "
                  "  AND substr(COALESCE(sent_at,''),1,10)=?",
                  (ящик, день)).fetchone()[0]
print("\n=== ЖИВОЙ IMAP: %s ===" % ящик)
cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
папки = mb.folders(ящик)


def раскод(н):
    import base64
    вых, буф, внутри = [], "", False
    for сим in str(н):
        if внутри:
            if сим == "-":
                вых.append("&" if not буф else base64.b64decode(
                    buf_pad(буф.replace(",", "/"))).decode("utf-16-be"))
                буф, внутри = "", False
            else:
                буф += сим
        elif сим == "&":
            внутри = True
        else:
            вых.append(сим)
    return "".join(вых)


def buf_pad(б):
    return б + "=" * ((4 - len(б) % 4) % 4)


print("папки:")
имена = []
for п in папки:
    н = п if isinstance(п, str) else (п.get("name") or str(п))
    имена.append(н)
    print("   %-46s %s" % (н, раскод(н)))
имя = None
for н in имена:
    if "sent" in н.lower() or "отправлен" in раскод(н).lower():
        имя = н
        break
print("\nпапка отправленных: %s" % (имя or "НЕ НАЙДЕНА"))
if имя:
    письма = mb.messages(ящик, folder=имя, limit=30)
    print("писем в ней (последние 30): %d" % len(письма))
    даты = Counter(str(п.get("date") or "")[:16] for п in письма)
    for к, н in list(даты.items())[:10]:
        print("   %-22s %3d" % (к, н))
    for п in письма[:5]:
        print("   • %s | %s" % (str(п.get("date"))[:22],
                                str(п.get("subject"))[:56]))
print("\nа по базе с этого ящика за %s ушло: %d писем" % (день, наших))
