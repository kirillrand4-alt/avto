# -*- coding: utf-8 -*-
"""Откуда адреса закупщиков КЦ «без имени» (по журналу zakupshchiki-imena.jsonl): source, есть ли
source_url, домен источника = сайт компании, свежесть updated_at, примеры."""
import collections, io, json, sqlite3
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
сайт = {str(i): str(x or "").lower().split("//")[-1].split("/")[0].replace("www.", "") for i, x in e.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL")}
сч = collections.Counter(); пр = collections.defaultdict(list); год = collections.Counter(); комп = set()
for с in io.open(r"C:\sender\_ops\zakupshchiki-imena.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з["napr"] != "КЦ" or not з["reshenie"].startswith("без"): continue
    комп.add(з["inn"])
    r = e.execute("SELECT source, COALESCE(source_url,''), COALESCE(updated_at,'') FROM emails WHERE inn=? AND lower(email)=?", (з["inn"], з["email"])).fetchone() or ("?", "", "")
    src, url, upd = r
    тип = "url: сайт компании" if url and сайт.get(з["inn"]) and сайт[з["inn"]] in url.lower() else ("url: сторонний" if url.startswith("http") else ("без url" if not url else "url: " + url[:20]))
    сч[(src or "-", тип)] += 1; год[upd[:7]] += 1
    if len(пр[(src, тип)]) < 2: пр[(src, тип)].append((з["email"], url[:90]))
print("компаний:", len(комп), "| адресов:", sum(сч.values()))
for к, v in сч.most_common(15): print("  %5d  %s" % (v, к), пр[к][:1])
print("месяц обновления:", sorted(год.items())[-8:])
