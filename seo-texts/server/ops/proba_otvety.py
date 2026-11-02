# -*- coding: utf-8 -*-
"""Ответы пробы по адресам из журнала прогона (только чтение): proba_otvety.py <журнал.jsonl> [N]"""
import io, json, sqlite3, sys
from collections import Counter
з = [json.loads(s) for s in io.open(sys.argv[1], encoding="utf-8")]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 15
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
сч = Counter()
for x in з:
    р = c.execute("SELECT verdict, answer, mx, ts FROM addr_probe WHERE lower(email)=?", (x["email"],)).fetchone()
    сч[(р[0] if р else None, (str(р[1]) if р else "")[:60])] += 1
for к, n in сч.most_common(N):
    print(n, к)
д = Counter(x["email"].split("@")[-1] for x in з)
print("домены:", д.most_common(12))
р = c.execute("SELECT answer FROM addr_probe WHERE verdict='неясно' AND answer LIKE 'MX не найден%' ORDER BY ts DESC LIMIT 1").fetchone()
print("полный ответ:", р[0] if р else None)
print("такие вердикты за сутки во всей базе:", c.execute("SELECT count(*) FROM addr_probe WHERE answer LIKE 'MX не найден%' AND ts >= datetime('now','-1 day')").fetchone())
