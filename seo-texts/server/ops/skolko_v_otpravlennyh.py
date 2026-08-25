# -*- coding: utf-8 -*-
"""Сколько писем лежит в «Отправленных» ящиков — размер работы для разбора.

Владелец спросил, сложно ли научить сторожа подтягивать ручные ответы из
веб-почты. Цена вопроса зависит от того, сколько там писем и сколько из них
наши собственные (их узнаём по Message-ID, он уже лежит в messages).
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402
from sender.v_otpravlennye import dekodirovat  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
наши = {(р[0] or "").strip("<> ") for р in c.execute(
    "SELECT rfc_message_id FROM messages WHERE rfc_message_id IS NOT NULL")}
print("Message-ID наших писем в базе: %d\n" % len(наши))

итого = свои = чужие = 0
for ящик in [x.mailbox_id for x in cfg.mailboxes()]:
    try:
        папки = mb.folders(ящик)
    except Exception as e:  # noqa: BLE001
        print("   %-38s папки не прочитались: %s" % (ящик, str(e)[:40]))
        continue
    имя = None
    for п in папки:
        н = п if isinstance(п, str) else (п.get("name") or "")
        if "sent" in н.lower() or "отправлен" in dekodirovat(н).lower():
            имя = н
            break
    if not имя:
        print("   %-38s папка не найдена" % ящик)
        continue
    try:
        r = mb.messages(ящик, folder=имя, limit=200)
    except Exception as e:  # noqa: BLE001
        print("   %-38s не читается: %s" % (ящик, str(e)[:40]))
        continue
    письма = r.get("messages") or []
    с = sum(1 for п in письма
            if str(п.get("message_id") or "").strip("<> ") in наши)
    ч = len(письма) - с
    итого += r.get("total") or 0
    свои += с
    чужие += ч
    print("   %-38s всего %4d | из показанных наших %3d, ручных %3d"
          % (ящик, r.get("total") or 0, с, ч))
print("\nвсего в «Отправленных» по всем ящикам: %d" % итого)
print("в просмотренной выборке: наших %d, написанных руками %d" % (свои, чужие))
