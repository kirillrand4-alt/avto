# -*- coding: utf-8 -*-
"""1) Событие 446320 «входящее вне переписки»: от кого, на какой ящик, писали ли мы этому адресу/домену, почему не привязалось.
2) Пересечение кампаний 20/21/22 в расписании: один адрес / один ИНН получит два письма КЦ? Только чтение (адреса не печатаем целиком)."""
import json, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
тб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
кол = [r[1] for r in c.execute("PRAGMA table_info(events)")] if "events" in тб else []
print("events колонки:", кол)
р = c.execute("SELECT * FROM events WHERE id=446320").fetchone() if кол else None
д = dict(zip(кол, р)) if р else {}
for к, v in д.items():
    if к not in ("body", "raw", "html"): print("  ", к, "=", str(v)[:300])
мета = {}
for к in ("payload", "data", "meta", "details"):
    if д.get(к):
        try: мета = json.loads(д[к]); break
        except Exception: pass
от = str(мета.get("from") or мета.get("from_addr") or мета.get("sender") or "").lower()
print("от:", от, "| ключи payload:", list(мета)[:25])
if "@" in от:
    дом = от.split("@")[-1].strip(">")
    print("писали этому адресу:", c.execute("SELECT m.campaign_id, m.status, m.sent_at, m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=?", (от.strip("<>"),)).fetchall()[:5])
    print("писали на домен:", c.execute("SELECT m.campaign_id, m.status, m.sent_at, m.mailbox_id, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email) LIKE ? AND m.status='sent' ORDER BY m.sent_at DESC LIMIT 5", ("%@" + дом,)).fetchall())
# 2) пересечения
def карта(камп):
    return {r[0]: r[1] for r in c.execute("SELECT lower(r.email), COALESCE(r.inn,'') FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=? AND m.status IN ('scheduled','sent')", (камп,))}
к = {x: карта(x) for x in (20, 21, 22)}
for a, b in ((20, 21), (20, 22), (21, 22)):
    об_адр = set(к[a]) & set(к[b]); иа = {v for v in к[a].values() if v}; иб = {v for v in к[b].values() if v}
    print("кампании %d и %d: общих адресов %d, общих ИНН %d" % (a, b, len(об_адр), len(иа & иб)))
