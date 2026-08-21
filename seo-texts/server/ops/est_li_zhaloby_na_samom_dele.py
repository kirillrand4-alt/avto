# -*- coding: utf-8 -*-
"""Жалобы: приходят и теряются - или не приходят вовсе?

Я сказал «FBL не подключён», проверив ровно одно: событий complaint ноль.
Этого мало. Разбор входящей почты жалобы УМЕЕТ ловить (imap_watcher.
_is_complaint смотрит content_type message/feedback-report - это и есть
формат FBL - плюс слова abuse/spam/complaint). Значит вопрос в другом:
доходят ли до наших ящиков сами отчёты.

Смотрим: события kind='other' (их 115) - от кого и с какой темой, нет ли
среди них отчётов, которые разбор не узнал; и лежит ли в наших ящиках
что-нибудь похожее на FBL.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT id, event_type, mailbox_id, substr(event_ts,1,16) когда, "
    "       COALESCE(detail_json,'') dj FROM events "
    " WHERE event_type IN ('other','complaint','skip') ORDER BY id DESC"
).fetchall()
print(f"событий other/complaint/skip: {len(ряды)}")

отправители, темы = Counter(), Counter()
подозрительные = []
for р in ряды:
    try:
        д = json.loads(р["dj"] or "{}")
    except Exception:                                              # noqa: BLE001
        д = {}
    плоско = json.dumps(д, ensure_ascii=False).lower()
    заг = д.get("headers") or {}
    отпр = str(заг.get("From") or д.get("from") or "")[:60]
    тема = str(заг.get("Subject") or д.get("subject") or "")[:70]
    if отпр:
        отправители[отпр] += 1
    if тема:
        темы[тема] += 1
    if any(м in плоско for м in ("feedback-report", "abuse", "complaint",
                                 "жалоб", "spam report")):
        подозрительные.append((р["id"], р["event_type"], р["когда"], отпр, тема))

print("\nтоп отправителей в этих событиях:")
for о, н in отправители.most_common(10):
    print(f"  {н:>4}  {о}")
print("\nтоп тем:")
for т, н in темы.most_common(10):
    print(f"  {н:>4}  {т}")
print(f"\nпохожих на жалобу/FBL: {len(подозрительные)}")
for п in подозрительные[:10]:
    print(f"  #{п[0]} {п[1]} {п[2]} от {п[3]} :: {п[4]}")

# чем панель разбирает входящую: какие ящики читаются
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
print(f"\nчитаемых ящиков (IMAP): {len(list(cfg.mailboxes()))}")
print("адреса вида abuse@/postmaster@ среди них:",
      [mb.mailbox_id for mb in cfg.mailboxes()
       if mb.mailbox_id.split("@")[0] in ("abuse", "postmaster", "fbl")] or "нет")
print("auto_suppress_on_complaint:", cfg.get("imap.auto_suppress_on_complaint", "(нет ключа)"))
