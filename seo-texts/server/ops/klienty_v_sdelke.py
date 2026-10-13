# -*- coding: utf-8 -*-
"""Клиенты с активной сделкой Meyer — холодных не шлём (записка соседней сессии 13.10).

Вход: _ops/sdelki-klienty.json (почты сайтов клиентов в сделке, домены их
сайтов, ИНН в базе и ИНН компании сделки). Находим получателей по почте,
домену сайта/почты и ИНН (служебный ИНН — через сайт компании в enrich).
С --primenit: письма в очереди → skipped, ИНН → реестр «не наш адресат»
(«клиент с активной сделкой Meyer»; стоп-лист не трогаем — он режет и ответы), решение «наш или нет» → источник «реестр».
"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender\server\ops")
sys.path.insert(0, r"C:\sender")
ПРИМЕНИТЬ = "--primenit" in sys.argv
д = json.load(io.open(r"C:\sender\_ops\sdelki-klienty.json", encoding="utf-8"))
почты, домены, инны = set(д["почты"]), set(д["домены"]), set(д["инны"])
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
for inn, site in cx.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL AND site<>''"):
    if str(site).lower().replace("www.", "").split("/")[0] in домены:
        инны.add(str(inn))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
получатели = [dict(р) for р in c.execute("SELECT id, inn, lower(email) e, company_name FROM recipients")
              if (р["e"] in почты or str(р["e"] or "").rsplit("@", 1)[-1] in домены or str(р["inn"] or "") in инны)]
ид = [р["id"] for р in получатели]
очередь = [dict(р) for р in c.execute(
    "SELECT id, status, campaign_id, recipient_id FROM messages WHERE status IN ('pending_review','scheduled') "
    "AND recipient_id IN (%s)" % (",".join(map(str, ид)) or "0"))]
ушло = c.execute("SELECT count(*) FROM messages WHERE status='sent' AND recipient_id IN (%s)" % (",".join(map(str, ид)) or "0")).fetchone()[0]
print("получателей, связанных с клиентами в сделке: %d (ИНН %d, почт %d, доменов %d)" % (len(получатели), len(инны), len(почты), len(домены)))
print("писем в очереди: %d (%s); уже уходило писем: %d" % (len(очередь), {s: sum(1 for x in очередь if x['status'] == s) for s in ('pending_review', 'scheduled')}, ушло))
for р in получатели[:8]:
    print("   %s <%s> ИНН %s" % (str(р["company_name"])[:34], р["e"], р["inn"]))
if ПРИМЕНИТЬ:
    т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        n = c.executemany("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN "
                          "('pending_review','scheduled')", [("снято 13.10: клиент с активной сделкой Meyer", т, x["id"]) for x in очередь]).rowcount
    # НЕ стоп-лист: он режет и наши ответы клиенту в переписке. Реестр
    # «не наш адресат» запрещает только холодную генерацию (и панель, и прогоны).
    from sender.ne_nash import build_ne_nash
    реестр = build_ne_nash()
    инны_все = инны | {str(р["inn"]) for р in получатели if р["inn"]}
    внесено = sum(1 for инн in инны_все if реестр.записать(инн, "клиент с активной сделкой Meyer", "записка соседа 13.10"))
    инны = инны_все
    import verdikty_v_bazy as вб
    вб.obnovit([{"inn": i, "rusprom": "клиент в сделке", "napr": "мейер", "pochemu": "активная сделка Meyer (записка соседа 13.10)",
                 "istochnik": "реестр"} for i in инны])
    print("снято писем: %d; в реестр «не наш» внесено ИНН: %d" % (n, внесено))
print("=== КЛИЕНТЫ В СДЕЛКЕ: %s ===" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
