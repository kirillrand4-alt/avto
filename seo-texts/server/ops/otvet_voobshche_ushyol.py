# -*- coding: utf-8 -*-
"""Ответ вообще уходил по SMTP или только записался.

Если панель зовёт отправителя в dry_run, письмо уезжает в песочницу, а
учёт при этом пишется как при настоящей отправке: событие reply_sent есть,
строка в messages есть, а у клиента письма нет и в «Отправленных» тоже.
Проверяем настройку, а не догадку.
"""
import io
import re
import sqlite3

т = io.open(r"C:\sender\sender.yaml", encoding="utf-8", errors="replace").read()
for ключ in ("dry_run", "live_send", "sandbox", "smtp_host"):
    for м in re.finditer(r"^\s*%s\s*:.*$" % ключ, т, re.M):
        print("sender.yaml| %s" % м.group(0).strip())

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("\npanel_settings:")
for р in c.execute("SELECT key, value FROM panel_settings"):
    if any(с in р["key"] for с in ("send", "dry", "live", "confirm", "auto")):
        print("   %-28s %s" % (р["key"], str(р["value"])[:120]))

print("\nsend_log по ответам (outcome=reply_sent):")
for р in c.execute("SELECT ts, email, rfc_message_id, subject FROM send_log "
                   " WHERE outcome='reply_sent' ORDER BY ts DESC LIMIT 5"):
    print("   %s %-34s %s" % (str(р["ts"])[:19], str(р["email"])[:34],
                              str(р["subject"])[:44]))

print("\nответы как письма в messages:")
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.rfc_message_id, "
        "       r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.idempotency_key LIKE 'otvet%' OR m.subject LIKE 'Re:%' "
        " ORDER BY m.id DESC LIMIT 6"):
    print("   #%-6s %-9s %s %-32s %s" % (р["id"], р["status"],
                                         str(р["sent_at"])[:19],
                                         str(р["email"])[:32],
                                         str(р["rfc_message_id"])[:40]))
