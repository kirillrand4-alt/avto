# -*- coding: utf-8 -*-
"""Свежие приговоры «нет MX»/«нет ящика» за последние 2 суток: сколько, откуда (только чтение);
   с --otkatit-pereproba возвращает «неясно» адресам, которым «нет MX» поставила перепроба 12.11 при сломанном DNS."""
import io, json, sqlite3, sys, time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for v in ("нет MX", "нет ящика"):
    р = c.execute("SELECT source, COUNT(*), MIN(ts), MAX(ts) FROM addr_probe WHERE verdict=? AND ts>='2026-11-11' GROUP BY source", (v,)).fetchall()
    print(v, "с 11.11:", р)
print("последние 5 проб:", c.execute("SELECT verdict, source, ts, substr(answer,1,60) FROM addr_probe ORDER BY ts DESC LIMIT 5").fetchall())
мои = [json.loads(с) for с in io.open(r"C:\sender\_ops\gaz-pereproba-neyasnyh.jsonl", encoding="utf-8")]
плохие = [з["email"] for з in мои if з["itog"] in ("нет MX", "нет ящика")]
print("приговоры перепробы:", плохие)
if "--otkatit-pereproba" in sys.argv:
    for em in плохие:
        c.execute("UPDATE addr_probe SET verdict='неясно', answer='откат: DNS сервера не отдавал MX 12.11' WHERE lower(email)=?", (em,))
        cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
        cx.execute("UPDATE emails SET probe_verdict='неясно', probe_answer='откат: DNS сервера сломан 12.11' WHERE lower(email)=?", (em,)); cx.commit()
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("UPDATE email_probe SET verdict='неясно', answer='откат: DNS сервера сломан 12.11' WHERE email=?", (em,)); ox.commit()
    c.commit(); print("откатено:", len(плохие))
