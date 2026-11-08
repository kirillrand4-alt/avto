# -*- coding: utf-8 -*-
"""Почему адрес «закреплён за другим ИНН» не прошёл как общая почта группы (08.11)."""
import io, json, re, sqlite3, collections
к = sqlite3.connect(r"C:\sender\sender.db"); e = sqlite3.connect(r"C:\sender\enrich.db")
def ядро(н):
    н = re.sub(r"(?i)общество с ограниченной ответственностью|акционерное общество|публичное|непубличное|\b(ооо|ао|пао|зао|оао|нпо|нпп|гк|пк|тк|ск|нпц|ип)\b|[«»\"'()\-.,]", " ", str(н or ""))
    return " ".join(н.lower().split())
def имя(inn):
    return (e.execute("SELECT name FROM companies WHERE inn=?", (inn,)).fetchone() or [""])[0]
в_очереди = {str(x[0]) for x in к.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','sending','pending_review')")}
c = collections.Counter(); пр = collections.defaultdict(list)
for l in io.open(r"C:\sender\_ops\zakupshchiki-kc.jsonl", encoding="utf-8"):
    try: d = json.loads(l)
    except Exception: continue
    if d.get("ts", "") < "2026-11-08T15:00" or not d.get("otsev", "").startswith("адрес закреплён"): continue
    em = d["email"].lower()
    r = к.execute("SELECT inn, company_name FROM recipients WHERE lower(email)=?", (em,)).fetchone()
    наше, их = ядро(имя(d["inn"])), ядро((r[1] if r else "") or имя(str(r[0]) if r else ""))
    совп = bool(наше and их and (наше == их or наше in их or их in наше))
    писали = к.execute("SELECT max(ts) FROM send_log WHERE outcome='sent' AND lower(email)=?", (em,)).fetchone()[0]
    ключ = ("имена совпали" if совп else "имена разные") + (" | писали на адрес" if писали else "") + (" | ИНН панели в очереди" if r and str(r[0]) in в_очереди else "")
    c[ключ] += 1
    if len(пр[ключ]) < 4: пр[ключ].append((наше[:40], их[:40], (писали or "")[:10]))
for k, v in c.most_common(): print(v, k)
for k, v in пр.items(): print("--", k); [print("   ", x) for x in v]
