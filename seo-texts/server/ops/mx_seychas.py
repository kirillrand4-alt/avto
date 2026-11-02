# -*- coding: utf-8 -*-
"""Резолвится ли MX сейчас на сервере (только чтение): dnspython и nslookup."""
import subprocess
import dns.resolver
for д in ("mail.ru", "yandex.ru", "gmail.com", "bk.ru"):
    try:
        print(д, "dnspython:", [str(r.exchange) for r in dns.resolver.resolve(д, "MX", lifetime=10)][:2])
    except Exception as e:
        print(д, "dnspython ОШИБКА:", type(e).__name__, str(e)[:120])
print(subprocess.run(["nslookup", "-type=mx", "mail.ru"], capture_output=True, text=True, timeout=30).stdout[-400:])
print("резолверы:", dns.resolver.get_default_resolver().nameservers)
for ns in ("77.88.8.8", "8.8.8.8", "1.1.1.1", "188.93.16.19", "188.93.17.19", "10.0.2.3"):
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = [ns]
    try:
        print(ns, [str(x.exchange) for x in r.resolve("mail.ru", "MX", lifetime=8)][:1])
    except Exception as e:
        print(ns, "ОШИБКА", type(e).__name__)
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
print("приговоры «нет MX» по часам за 3 суток:", c.execute("SELECT substr(ts,1,13), count(*) FROM addr_probe WHERE verdict='нет MX' AND ts>=datetime('now','-3 day') GROUP BY 1 ORDER BY 1").fetchall())
print("примеры «нет MX» сегодня:", [r[0] for r in c.execute("SELECT email FROM addr_probe WHERE verdict='нет MX' AND ts>=date('now') LIMIT 15")])
