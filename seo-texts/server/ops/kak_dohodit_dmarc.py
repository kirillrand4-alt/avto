# -*- coding: utf-8 -*-
"""Как отчёт, адресованный dmarc@домен, попадает в наш читаемый ящик.

Панель читает 21 ящик, и dmarc@ среди них нет - но письма с To: dmarc@...
в журнале есть. Значит это ПЕРЕСЫЛКА (алиас), и механика уже работает.
Проверяем на конкретном письме: что в To, что в Delivered-To, и в каком
ящике панель его увидела.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
показано = 0
for р in c.execute("SELECT id, event_type, mailbox_id, substr(event_ts,1,16) когда, "
                   "COALESCE(detail_json,'') dj FROM events "
                   "WHERE COALESCE(detail_json,'') LIKE '%dmarc@%' "
                   "ORDER BY id DESC LIMIT 40"):
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        continue
    заг = д.get("headers") or {}
    if not isinstance(заг, dict):
        continue
    to = str(заг.get("To") or "")
    if "dmarc@" not in to.lower():
        continue
    print(f"\n#{р['id']} {р['event_type']} {р['когда']}")
    print(f"   ящик панели : {р['mailbox_id']}")
    for поле in ("To", "Delivered-To", "X-Original-To", "Envelope-To",
                 "From", "Subject", "Received"):
        з = str(заг.get(поле) or "")
        if з:
            print(f"   {поле:<14}: {з[:150]}")
    показано += 1
    if показано >= 3:
        break
if not показано:
    print("писем с To: dmarc@ в журнале не нашлось")
