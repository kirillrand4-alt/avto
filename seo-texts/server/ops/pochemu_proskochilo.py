# -*- coding: utf-8 -*-
"""Чем на самом деле плохи 182 забракованных: не тот адресат или выдумка."""
import io
import json
import sqlite3
from collections import Counter

нельзя = {}
for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
    except Exception:                                            # noqa: BLE001
        continue
    if str(d.get("verdikt")) == "не отправлять":
        нельзя[int(d["id"])] = d

вид = Counter()
for d in нельзя.values():
    не_тот = d.get("napravlenie_verno") is False
    выдумка = bool(str(d.get("vydumka") or "").strip())
    факты = d.get("fakty_verny") is False
    if не_тот and not выдумка:
        вид["адресат не тот (гейт мог бы поймать)"] += 1
    elif не_тот and выдумка:
        вид["и адресат не тот, и выдумка"] += 1
    elif выдумка or факты:
        вид["адресат годный, ВЫДУМАНА КОНКРЕТИКА"] += 1
    else:
        вид["прочее (язык, обращение, реклама)"] += 1
print("=== чем плохи 182 ===")
for к, n in вид.most_common():
    print("   %-42s %4d  (%.0f%%)" % (к, n, 100.0 * n / len(нельзя)))

# утечка: письмо ушло компании, которую гейт назвал «не покупатель»
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = str(d["inn"])
зн = ",".join("?" * len(партия))
инны = sorted(set(партия.values()))
зн2 = ",".join("?" * len(инны))
не_пок = {str(r[0]) for r in c.execute(
    "SELECT inn FROM target_verdicts WHERE verdict='не покупатель' "
    "  AND inn IN (%s)" % зн2, инны)}
print("")
print("=== утечка гейта ===")
print("компаний партии с вердиктом гейта «не покупатель»: %d" % len(не_пок))
if не_пок:
    зн3 = ",".join("?" * len(не_пок))
    for r in c.execute(
            "SELECT cr.id, cr.status, cr.email, r.company_name, "
            "       (SELECT pochemu FROM target_verdicts t WHERE t.inn=cr.inn) п "
            "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
            " WHERE cr.inn IN (%s) AND cr.id IN (%s)" % (зн3, зн),
            list(не_пок) + list(партия)):
        print("   rev %-6s %-9s %-26s %s" % (r["id"], r["status"],
                                             str(r["email"])[:26],
                                             str(r["company_name"] or "")[:30]))
        print("      гейт: %s" % str(r["п"] or "")[:100])
# сколько писем ВСЕЙ базы ушло тем, кого гейт назвал не покупателем
всего_не_пок = c.execute(
    "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' AND r.inn IN "
    "   (SELECT inn FROM target_verdicts WHERE verdict='не покупатель')"
).fetchone()[0]
print("")
print("по ВСЕЙ базе отправлено писем компаниям «не покупатель»: %d" % всего_не_пок)
c.close()
