# -*- coding: utf-8 -*-
"""КЦ-1: компании без ИНН (найдены поиском по сайту) — синтетический ИНН, как
делали для Meyer (владелец 20.10: «по Meyer таким синтетические ИНН писали»,
«это поиском в ПС найденные компании»).

* Ключ компании — её сайт/ключ из файла (inn_raw: «САЙТ:домен» или «000…»).
  Одна компания = один синтетический ИНН на все её адреса.
* Новый ряд: 11 цифр «00000100001…» — выше всего, что уже занято в панели
  (там 000-ряд до ~00000004000), чтобы не столкнуться с синтетикой Meyer:
  31 ключ «000…» из файла КЦ-1 совпал с ЧУЖОЙ компанией в панели.
* recipients.inn = синтетический, extra.inn_sintet = true (inn_raw остаётся).
* enrich.companies — строка компании (название, сайт, ОКВЭД, выручка, регион,
  продукция) из kc1-lesenka.json, чтобы генератор видел паспорт.
* enrich.emails запасные лесенки (source=kc-1-pochta) — перевязать на тот же ИНН.
Журнал — _ops/kc1-sintet-inn.jsonl. Без --primenit — счёт. Откат — --otkat."""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

ЖУР = r"C:\sender\_ops\kc1-sintet-inn.jsonl"
СТАРТ = 100001
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
if "--otkat" in sys.argv:
    n = 0
    with c, e:
        for s in io.open(ЖУР, encoding="utf-8"):
            z = json.loads(s)
            if z.get("что") == "получатель":
                c.execute("UPDATE recipients SET inn=NULL, extra_json=? WHERE id=?", (z["extra_bylo"], z["id"]))
                n += 1
            elif z.get("что") == "компания":
                e.execute("DELETE FROM companies WHERE inn=?", (z["inn"],))
            elif z.get("что") == "запасной":
                e.execute("UPDATE emails SET inn=? WHERE inn=? AND lower(email)=?", (z["bylo"], z["inn"], z["email"]))
    print("откат: получателей", n)
    sys.exit()

занято = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL")}
занято |= {str(r[0]) for r in e.execute("SELECT inn FROM companies")}
ряды = []
for rid, em, ex, имя in c.execute("SELECT id, lower(email), extra_json, company_name FROM recipients "
                                  "WHERE inn IS NULL AND extra_json LIKE '%КЦ-1%'"):
    x = json.loads(ex or "{}")
    if "КЦ-1" in (x.get("gruppy") or []):
        x.setdefault("_имя", имя)
        ряды.append((rid, em, ex, x))
# данные компаний из файла заливки
лес = json.load(io.open(r"C:\seostat\drop\drop-storage\kc1-lesenka.json", encoding="utf-8"))
главные = лес["главные"] if isinstance(лес, dict) else лес
запас = лес.get("запас", []) if isinstance(лес, dict) else []
по_адресу = {str(z.get("email") or "").strip().lower(): z for z in главные}
по_ключу = {str(z.get("inn_raw") or "").strip().lower(): z for z in главные if not z.get("inn") and z.get("inn_raw")}
print("пример строки файла:", {k: (str(v)[:40] if v else v) for k, v in (главные[0] if главные else {}).items()})


def ключ(x, em):
    raw = str(x.get("inn_raw") or "").strip()
    if raw:
        return raw.lower()
    сайт = re.sub(r"^www\.", "", str(x.get("site") or "").lower().split("//")[-1].split("/")[0])
    return "сайт:" + (сайт or em.split("@")[-1])


ключи = {}
сл = СТАРТ
план = []
for rid, em, ex, x in ряды:
    к = ключ(x, em)
    if к not in ключи:
        while ("%011d" % сл) in занято:
            сл += 1
        ключи[к] = "%011d" % сл
        занято.add(ключи[к])
        сл += 1
    план.append((rid, em, ex, x, к, ключи[к]))
кол_c = {r[1] for r in e.execute("PRAGMA table_info(companies)")}
компании = {}
for rid, em, ex, x, к, inn in план:
    z = по_ключу.get(к) or по_адресу.get(em) or {}
    if inn in компании:
        continue
    # Данные: файл заливки (по ключу/адресу), иначе — то, что легло в карточку
    # получателя при заливке (название, сайт, отрасль).
    поля = {"inn": inn, "name": z.get("name") or x.get("_имя"), "site": z.get("site") or x.get("site"),
            "okved": z.get("okved"), "revenue_rub": z.get("revenue") or x.get("revenue_rub"), "region": z.get("region"),
            "activity": "; ".join(v for v in (z.get("produkciya"), z.get("oborud")) if v) or x.get("otrasl") or None}
    компании[inn] = {k: v for k, v in поля.items() if v and k in кол_c}
сырые = set(ключи)
зап = [a for a in запас if str(a.get("inn") or "").strip().lower() in сырые]
print("получателей КЦ-1 без ИНН:", len(ряды), "| компаний (ключей):", len(ключи),
      "| ряд ИНН: %s … %s" % (min(ключи.values(), default="-"), max(ключи.values(), default="-")))
print("с названием:", sum(1 for v in компании.values() if v.get("name")), "| с продукцией/отраслью:",
      sum(1 for v in компании.values() if v.get("activity")), "| с сайтом:", sum(1 for v in компании.values() if v.get("site")), "из", len(компании),
      "| запасных адресов перевязать:", len(зап))
print("ключи по виду:", Counter("сайт" if k.startswith("сайт") else "000" if k.startswith("000") else "прочее" for k in ключи))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
ж = io.open(ЖУР, "a", encoding="utf-8")
т = time.strftime("%Y-%m-%dT%H:%M:%S")
for i in range(0, len(план), 300):
    кус = план[i:i + 300]
    with c:
        for rid, em, ex, x, к, inn in кус:
            x2 = {kk: vv for kk, vv in x.items() if kk != "_имя"}
            x2.update(inn_sintet=True, inn_klyuch=к)
            c.execute("UPDATE recipients SET inn=?, extra_json=?, updated_at=? WHERE id=? AND inn IS NULL",
                      (inn, json.dumps(x2, ensure_ascii=False), т, rid))
            ж.write(json.dumps({"что": "получатель", "id": rid, "inn": inn, "extra_bylo": ex}, ensure_ascii=False) + "\n")
with e:
    for inn, п in компании.items():
        e.execute("INSERT OR IGNORE INTO companies (%s) VALUES (%s)" % (",".join(п), ",".join("?" * len(п))), list(п.values()))
        ж.write(json.dumps({"что": "компания", "inn": inn}) + "\n")
    for a in зап:
        к = str(a.get("inn") or "").strip()
        inn = ключи[к.lower()]
        e.execute("UPDATE emails SET inn=? WHERE inn=? AND lower(email)=?", (inn, к, str(a["email"]).lower()))
        ж.write(json.dumps({"что": "запасной", "inn": inn, "bylo": к, "email": str(a["email"]).lower()}, ensure_ascii=False) + "\n")
ж.flush()
os.fsync(ж.fileno())
ж.close()
print("ПРИМЕНЕНО: получателей", len(план), "компаний", len(компании), "запасных", len(зап))
