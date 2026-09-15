# -*- coding: utf-8 -*-
"""С какого адреса пришёл ответ ТОП ФУД: заголовки письма, а не карточка.

В карточке лида показан адрес ПОЛУЧАТЕЛЯ (кому мы писали). Реальный
отправитель ответа живёт в заголовке From самого письма и в поле otvetil
карточки. Смотрим оба, плюс живой ящик по IMAP.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.mailbrowser import MailBrowser                      # noqa: E402

ЯЩИК = "v.ivanov@optic-sort.ru"
ИСКАТЬ = "topfood"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
вых = []
with store._lock:
    c = store._conn
    вых.append("--- получатели с доменом topfood ---")
    кол_п = [x[1] for x in c.execute("PRAGMA table_info(recipients)")]
    имя_к = next((x for x in ("contact_name", "person", "fio") if x in кол_п), None)
    for р in c.execute("SELECT * FROM recipients WHERE email LIKE ?",
                       ("%topfood%",)):
        вых.append("   #%-7s %-26s %-28s ИНН %s  контакт: %s"
                   % (р["id"], р["email"], str(р["company_name"])[:28],
                      р["inn"], str((р[имя_к] if имя_к else "") or "-")[:30]))

    вых.append("")
    вых.append("--- что мы им слали ---")
    for р in c.execute(
            "SELECT m.id, m.status, m.subject, m.sent_at, m.mailbox_id, "
            "       r.email FROM messages m JOIN recipients r "
            "    ON m.recipient_id=r.id WHERE r.email LIKE ? ORDER BY m.id",
            ("%topfood%",)):
        вых.append("   письмо %-7s %-8s %s -> %s"
                   % (р["id"], р["status"], str(р["sent_at"])[:16], р["email"]))
        вых.append("       с ящика %-34s тема: %s"
                   % (р["mailbox_id"], str(р["subject"])[:50]))

    вых.append("")
    вых.append("--- заголовки входящего из журнала событий ---")
    for р in c.execute(
            "SELECT e.id, e.event_type, e.event_ts, e.mailbox_id, e.detail_json "
            "  FROM events e JOIN recipients r ON e.recipient_id=r.id "
            " WHERE r.email LIKE ? AND e.event_type IN ('reply','reply_auto') "
            " ORDER BY e.id", ("%topfood%",)):
        вых.append("   событие #%s  %s  ящик %s"
                   % (р["id"], str(р["event_ts"])[:19], р["mailbox_id"]))
        try:
            д = json.loads(р["detail_json"] or "{}")
        except Exception:                                       # noqa: BLE001
            д = {}
        ш = д.get("headers") or {}
        for имя in ("From", "Reply-To", "Return-Path", "Sender", "To", "Cc",
                    "Subject", "Message-ID", "In-Reply-To"):
            if ш.get(имя):
                вых.append("       %-12s %s" % (имя, str(ш[имя])[:100]))

    вых.append("")
    вых.append("--- карточка лида ---")
    кол = [x[1] for x in c.execute("PRAGMA table_info(leads)")]
    for р in c.execute("SELECT * FROM leads WHERE email LIKE ? OR "
                       " company_name LIKE ?", ("%topfood%", "%ТОП ФУД%")):
        for k in кол:
            з = р[k]
            if з in (None, "") or k in ("need",):
                continue
            вых.append("   %-16s %s" % (k, str(з)[:110]))

вых.append("")
вых.append("--- живьём в ящике %s ---" % ЯЩИК)
mb = MailBrowser(cfg)
try:
    for п in mb.folders(ЯЩИК):
        имя = п.get("name")
        рез = mb.messages(ЯЩИК, folder=имя, limit=10, search=ИСКАТЬ)
        for м in рез.get("messages") or []:
            вых.append("   папка %-12s %s" % (п.get("title"), str(м.get("date"))[:31]))
            вых.append("       From: %s <%s>" % (str(м.get("from_name"))[:40],
                                                 м.get("from_addr")))
            вых.append("       To:   %s" % м.get("to_addr"))
            вых.append("       Тема: %s" % str(м.get("subject"))[:70])
except Exception as ex:                                         # noqa: BLE001
    вых.append("   не прочиталось: %s" % str(ex)[:120])

print("\n".join(вых))
print("")
print("=" * 74)
print("=== С КАКОГО АДРЕСА ОТВЕТИЛ ТОП ФУД ===")
