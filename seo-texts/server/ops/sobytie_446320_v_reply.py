# -*- coding: utf-8 -*-
"""Событие 446320 — ответ ООО «Натрули» (ИНН 5009117027) на письмо Meyer 49947 (кампания 14, ящик a.miroshnichenko,
отправлено 12.11 07:26 МСК на natruli@mail.ru). Сотрудник ответил НОВЫМ письмом с личного giga004@mail.ru, без темы и
In-Reply-To — поэтому панель не смогла привязать (тип 'other'). Привязываем к получателю/письму 49947 как reply.
    sobytie_446320_v_reply.py [--katit]"""
import sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
cfg = Config.load(r"C:\sender\sender.yaml"); store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
м = c.execute("SELECT id, recipient_id, campaign_id, mailbox_id FROM messages WHERE id=49947").fetchone()
е = c.execute("SELECT event_type, recipient_id, message_id FROM events WHERE id=446320").fetchone()
print("письмо:", м, "| событие было:", е); c.close()
if "--katit" in sys.argv:
    with store.transaction() as conn:
        n = conn.execute("UPDATE events SET event_type='reply', recipient_id=?, message_id=?, campaign_id=? WHERE id=446320 AND event_type='other'",
                         (м[1], м[0], м[2])).rowcount
    print("привязано: %d" % n)
    try:
        т = store.dialog_thread(м[1]); сп = т if isinstance(т, list) else (т.get("items") if isinstance(т, dict) else [])
        print("в переписке записей: %d" % len(сп or []))
    except Exception as ex: print("dialog_thread:", str(ex)[:100])
