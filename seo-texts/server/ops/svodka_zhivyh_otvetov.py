# -*- coding: utf-8 -*-
"""Ответы живых людей по дням — по ДАТЕ ПИСЬМА и без повторных записей.

Считаем не по event_ts (журнал сейчас перечитывает почтовый архив заново, и
отметка «когда заметили» пляшет), а по заголовку Date самого письма. Дубли
склеиваем по Message-ID, а где его нет — по ящику, получателю и началу текста.
"""
import json
import sqlite3
from collections import Counter, defaultdict
from email.utils import parsedate_to_datetime
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row

письма = {}
for r in c.execute(
        "SELECT e.id, e.event_type, e.event_ts, e.mailbox_id, e.detail_json, "
        "       e.recipient_id, r.company_name, r.email FROM events e "
        "  LEFT JOIN recipients r ON r.id = e.recipient_id "
        " WHERE e.event_type IN ('reply','reply_auto') ORDER BY e.id"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    h = d.get("headers") or {}
    mid = str(h.get("Message-ID") or "").strip()
    текст = " ".join(str(d.get("snippet") or "").split())
    ящик = str(r["mailbox_id"] or "")
    ключ = ("mid", ящик, mid) if mid else ("txt", ящик, str(r["recipient_id"]),
                                           текст[:200])
    день = str(r["event_ts"])[:10]
    дата = str(h.get("Date") or "")
    if дата:
        try:
            день = parsedate_to_datetime(дата).strftime("%Y-%m-%d")
        except Exception:
            pass
    письма.setdefault(ключ, dict(
        тип=r["event_type"], день=день, метка=str(d.get("reply_kind") or "—"),
        кто=str(r["company_name"] or r["email"] or "—")[:36], текст=текст[:70]))

по_дням = defaultdict(Counter)
метки = Counter()
живые = defaultdict(list)
for з in письма.values():
    д = з["день"]
    if з["тип"] == "reply_auto":
        по_дням[д]["авто"] += 1
        continue
    по_дням[д]["живые"] += 1
    по_дням[д][з["метка"]] += 1
    метки[з["метка"]] += 1
    живые[д].append(з)

print("=== кто ответил, по дням ===")
for д in sorted(живые):
    print("--- %s — %d живых ответов ---" % (д, len(живые[д])))
    for з in sorted(живые[д], key=lambda x: x["метка"]):
        print("   %-36s %-15s %s" % (з["кто"], з["метка"], з["текст"]))

ВИДЫ = [м for м, _ in метки.most_common()]
print()
print("=== ОТВЕТЫ ЖИВЫХ ЛЮДЕЙ ПО ДНЯМ (по дате письма, без повторов) ===")
шапка = "%-12s %7s %7s   " % ("день", "живые", "авто")
шапка += "  ".join("%-14s" % в for в in ВИДЫ)
print(шапка)
итог = Counter()
for д in sorted(по_дням):
    с = по_дням[д]
    итог.update(с)
    print("%-12s %7d %7d   %s"
          % (д, с["живые"], с["авто"],
             "  ".join("%-14d" % с[в] for в in ВИДЫ)))
print("%-12s %7d %7d   %s"
      % ("ИТОГО", итог["живые"], итог["авто"],
         "  ".join("%-14d" % итог[в] for в in ВИДЫ)))
отпр = {}
for r in c.execute("SELECT substr(event_ts,1,10) AS д, COUNT(*) AS n FROM events "
                   " WHERE event_type='sent' GROUP BY 1"):
    отпр[r["д"]] = r["n"]
print()
print("%-12s %8s %8s %8s" % ("день", "отпр.", "живых", "доля"))
for д in sorted(по_дням):
    н = отпр.get(д, 0)
    ж = по_дням[д]["живые"]
    print("%-12s %8d %8d %7.2f%%" % (д, н, ж, (100.0 * ж / н) if н else 0.0))
c.close()
