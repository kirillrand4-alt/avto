# -*- coding: utf-8 -*-
"""Ответы ЖИВЫХ ЛЮДЕЙ по дням: без автоответчиков и без отбивок."""
import json
import sqlite3
from collections import defaultdict
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row

# какие вообще бывают метки
метки = defaultdict(int)
for r in c.execute("SELECT detail_json FROM events WHERE event_type='reply'"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    метки[str(d.get("reply_kind") or "—")] += 1
print("метки ответов в журнале: %s"
      % ", ".join("%s=%d" % кv for кv in sorted(метки.items(), key=lambda x: -x[1])))
print()

# признаки робота внутри event_type='reply' (машина, а не человек)
РОБОТ = ("автоответ", "автоматическ", "не отвечайте на это письмо",
         "отпуске", "out of office", "automatic reply", "ваше обращение",
         "зарегистрировано под номером", "данное сообщение сформировано",
         "please do not reply", "no-reply", "письмо сформировано автоматически")

по_дням = defaultdict(lambda: defaultdict(int))
живые_списком = defaultdict(list)
for r in c.execute(
        "SELECT e.id, e.event_type, e.event_ts, e.detail_json, r.email, "
        "       r.company_name FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type IN ('reply','reply_auto') "
        "   AND e.event_ts >= '2026-08-01' ORDER BY e.event_ts"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    день = str(r["event_ts"])[:10]
    if r["event_type"] == "reply_auto":
        по_дням[день]["авто"] += 1
        continue
    текст = " ".join(str(d.get("snippet") or "").split()).lower()
    тема = str((d.get("headers") or {}).get("Subject") or "").lower()
    if any(п in текст[:400] or п in тема for п in РОБОТ):
        по_дням[день]["робот"] += 1
        continue
    метка = str(d.get("reply_kind") or "—")
    по_дням[день]["живые"] += 1
    по_дням[день][метка] += 1
    живые_списком[день].append(
        (str(r["company_name"] or r["email"] or "")[:34], метка,
         " ".join(str(d.get("snippet") or "").split())[:70]))

print("=== живые ответы последних трёх дней ===")
for день in sorted(живые_списком)[-3:]:
    print("--- %s (%d) ---" % (день, len(живые_списком[день])))
    for имя, метка, текст in живые_списком[день]:
        print("   %-34s %-12s %s" % (имя, метка, текст))
c.close()

print()
ВИДЫ = ["interested", "forward", "later", "refusal", "not_a_buyer",
        "competitor", "unsubscribe", "—"]
есть = [в for в in ВИДЫ if any(по_дням[д].get(в) for д in по_дням)]
print("%-12s %7s %7s %7s   %s"
      % ("день", "живые", "авто", "роботы", "  ".join("%-11s" % в for в in есть)))
итог = defaultdict(int)
for день in sorted(по_дням):
    с = по_дням[день]
    for к, v in с.items():
        итог[к] += v
    print("%-12s %7d %7d %7d   %s"
          % (день, с.get("живые", 0), с.get("авто", 0), с.get("робот", 0),
             "  ".join("%-11d" % с.get(в, 0) for в in есть)))
print("%-12s %7d %7d %7d   %s"
      % ("ИТОГО", итог["живые"], итог["авто"], итог["робот"],
         "  ".join("%-11d" % итог[в] for в in есть)))
