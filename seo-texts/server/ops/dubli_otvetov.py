# -*- coding: utf-8 -*-
"""Дубли входящих событий: одно письмо — два события.

Опрос по UID сменил ключ дедупликации (был imap:{uidvalidity}:{ПОРЯДКОВЫЙ}:{вид},
стал imap:{uidvalidity}:{UID}:{вид}). На ящиках, где порядковый номер не совпадает
с UID, СТАРЫЕ письма пришли с новым ключом и легли в журнал второй раз.
Ищем по Message-ID письма — он один и тот же в обеих записях.
"""
import json
import sqlite3
from collections import defaultdict
БАЗА = r"C:\sender\sender.db"
ТИПЫ = ("reply", "reply_auto", "bounce", "complaint", "dsn")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_msgid = defaultdict(list)
без_id = 0
метки = ",".join("?" * len(ТИПЫ))
for r in c.execute("SELECT id, event_type, event_ts, mailbox_id, dedup_key, "
                   "       recipient_id, detail_json FROM events "
                   " WHERE event_type IN (%s) AND event_ts >= '2026-08-01'" % метки,
                   list(ТИПЫ)):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    mid = str(((d.get("headers") or {}).get("Message-ID") or "")).strip()
    if not mid:
        без_id += 1
        continue
    по_msgid[(mid, r["mailbox_id"] or "")].append(dict(
        id=r["id"], тип=r["event_type"], ts=str(r["event_ts"]),
        ключ=str(r["dedup_key"] or ""), rid=r["recipient_id"],
        zap=str(d.get("zapisano_ts") or "")))
дубли = {к: v for к, v in по_msgid.items() if len(v) > 1}
print("событий с Message-ID: %d, без него: %d" % (len(по_msgid), без_id))
print("ДУБЛЕЙ (одно письмо — больше одного события): %d" % len(дубли))
по_дням = defaultdict(int)
по_типам = defaultdict(int)
лишние = []
for (mid, ящик), список in дубли.items():
    список.sort(key=lambda x: x["id"])
    for э in список[1:]:
        лишние.append(э)
        по_дням[э["ts"][:10]] += 1
        по_типам[э["тип"]] += 1
print("лишних записей: %d" % len(лишние))
print("  по типам: %s" % dict(по_типам))
print("  по дням:  %s" % dict(sorted(по_дням.items())))
print()
print("=== примеры (первые 12) ===")
for (mid, ящик), список in list(дубли.items())[:12]:
    print("  %s | %s" % (mid[:60], ящик))
    for э in список:
        print("      ev=%-7s %-10s %s  ключ=%s  zapisano=%s"
              % (э["id"], э["тип"], э["ts"][:19], э["ключ"][:34], э["zap"][:19]))
c.close()
