# -*- coding: utf-8 -*-
"""Ноль жалоб — это «их нет» или «мы их не видим»?

Жалобой в панели считается только машинный отчёт ARF (message/feedback-report).
Такие отчёты приходят ТОЛЬКО тем, кто подписан на feedback loop почтовика, и
приходят они на abuse@/postmaster@ домена отправителя. Проверяем: подписаны ли
мы куда-то, читаем ли те ящики, и что при этом писали живые люди.
"""
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
НЕДОВОЛЬСТВО = (
    "удалите из рассылки", "удалите меня", "отпишите", "отписаться",
    "не присылайте", "не пишите", "не рассылайте", "уберите мой",
    "уберите меня", "уберите мои контакты", "уберите контакты",
    "исключите из рассылки", "прекратите", "спам", "жалоб",
    "куда вы пишете", "откуда у вас", "перестаньте")

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== ЧТО ВООБЩЕ ЕСТЬ В ЖУРНАЛЕ ===")
for r in c.execute("SELECT event_type, COUNT(*) n FROM events GROUP BY 1 "
                   " ORDER BY 2 DESC"):
    print("   %-14s %d" % (r["event_type"], r["n"]))

print("\n=== ПРИЧИНЫ В СТОП-ЛИСТЕ ===")
for r in c.execute("SELECT reason, COUNT(*) n FROM suppression GROUP BY 1 "
                   " ORDER BY 2 DESC LIMIT 14"):
    print("   %-42s %d" % (str(r["reason"])[:42], r["n"]))

print("\n=== ЖИВЫЕ ЛЮДИ, КОТОРЫЕ ВЫРАЗИЛИ НЕДОВОЛЬСТВО ===")
слова = Counter()
случаи = []
for r in c.execute("SELECT e.id, e.event_ts, e.detail_json, r.company_name, "
                   "       r.email FROM events e "
                   "  LEFT JOIN recipients r ON r.id=e.recipient_id "
                   " WHERE e.event_type IN ('reply','reply_auto') "
                   " ORDER BY e.event_ts"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    текст = " ".join(str(d.get("snippet") or "").split())
    низ = текст.lower()
    поймали = [с for с in НЕДОВОЛЬСТВО if с in низ[:700]]
    if поймали:
        for с in поймали:
            слова[с] += 1
        случаи.append((str(r["event_ts"])[:10],
                       str(r["company_name"] or r["email"] or "")[:32],
                       текст[:95]))
for д, кто, т in случаи:
    print("   %s %-32s %s" % (д, кто, т))
print("\n   всего таких писем: %d из %d ответов"
      % (len(случаи),
         c.execute("SELECT COUNT(*) FROM events WHERE event_type IN "
                   "  ('reply','reply_auto')").fetchone()[0]))
print("   по словам: %s" % dict(слова.most_common(10)))
c.close()

print("\n=== КУДА БЫ ПРИШЛА НАСТОЯЩАЯ ЖАЛОБА ===")
from sender.config import Config                                   # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
ящики = []
try:
    for м in cfg.mailboxes():
        имя = м.get("id") if isinstance(м, dict) else getattr(м, "id", str(м))
        ящики.append(str(имя))
except Exception as ex:
    print("   список ящиков не прочитать: %s" % ex)
print("   опрашиваем ящиков: %d" % len(ящики))
служебные = [я for я in ящики
             if re.match(r"^(abuse|postmaster|fbl|complaints)@", я.lower())]
print("   из них abuse@/postmaster@/fbl@: %s" % (служебные or "НИ ОДНОГО"))
for ключ in ("imap.auto_suppress_on_complaint", "fbl", "feedback_loop",
             "legal.unsub_http_enabled", "tracking.open_enabled",
             "legal.unsub_base_url"):
    try:
        print("   %-34s = %r" % (ключ, cfg.get(ключ, None)))
    except Exception as ex:
        print("   %-34s ? %s" % (ключ, ex))
домены = sorted({я.split("@")[-1] for я in ящики if "@" in я})
print("   домены отправки (%d): %s" % (len(домены), ", ".join(домены[:12])))
