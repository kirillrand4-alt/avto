# -*- coding: utf-8 -*-
"""Что на самом деле лежит в метке neutral: передали профильному или отказ."""
import json
import sqlite3
from collections import Counter, defaultdict
from email.utils import parsedate_to_datetime
БАЗА = r"C:\sender\sender.db"
ПЕРЕДАЛИ = ("перешл", "переслал", "передал", "направьте", "направляйте",
            "обращайтесь", "занимается", "свяжется", "адресуйте", "напишите на",
            "пишите на", "отправьте на", "профильн", "ответственн",
            "в снабжение", "в отдел", "мой зам", "коллег")
ОТКАЗ = ("не актуал", "неактуал", "не заинтересова", "не планируем",
         "не требуется", "не нуждаемся", "нет потребности", "не используем",
         "спасибо, нет", "нет, спасибо", "не интересует", "отказ",
         "удалите из рассылки", "отпишите", "не рассматриваем")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
видели = set()
группы = defaultdict(list)
по_дням = defaultdict(Counter)
for r in c.execute(
        "SELECT e.id, e.event_ts, e.mailbox_id, e.recipient_id, e.detail_json, "
        "       r.company_name, r.email FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='reply' ORDER BY e.id"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    if str(d.get("reply_kind") or "—") != "neutral":
        continue
    h = d.get("headers") or {}
    текст = " ".join(str(d.get("snippet") or "").split())
    mid = str(h.get("Message-ID") or "").strip()
    ключ = ("mid", str(r["mailbox_id"]), mid) if mid else (
        "txt", str(r["mailbox_id"]), str(r["recipient_id"]), текст[:200])
    if ключ in видели:
        continue
    видели.add(ключ)
    день = str(r["event_ts"])[:10]
    if h.get("Date"):
        try:
            день = parsedate_to_datetime(str(h["Date"])).strftime("%Y-%m-%d")
        except Exception:
            pass
    низ = текст.lower()[:500]
    if any(п in низ for п in ПЕРЕДАЛИ):
        вид = "передали профильному"
    elif any(п in низ for п in ОТКАЗ):
        вид = "отказ"
    else:
        вид = "непонятно"
    группы[вид].append((день, str(r["company_name"] or r["email"] or "")[:34],
                        текст[:80]))
    по_дням[день][вид] += 1
for вид in ("передали профильному", "отказ", "непонятно"):
    print("=== %s: %d ===" % (вид, len(группы[вид])))
    for д, кто, т in sorted(группы[вид])[-14:]:
        print("   %s %-34s %s" % (д, кто, т))
    print()
print("=== neutral по дням ===")
print("%-12s %22s %8s %11s" % ("день", "передали профильному", "отказ",
                               "непонятно"))
for д in sorted(по_дням):
    с = по_дням[д]
    print("%-12s %22d %8d %11d" % (д, с["передали профильному"], с["отказ"],
                                   с["непонятно"]))
всего = sum(len(v) for v in группы.values())
print("\nвсего neutral: %d — из них передали профильному %d, отказ %d, непонятно %d"
      % (всего, len(группы["передали профильному"]), len(группы["отказ"]),
         len(группы["непонятно"])))
c.close()
