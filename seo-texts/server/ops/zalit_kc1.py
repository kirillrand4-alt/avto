# -*- coding: utf-8 -*-
"""Залить базу «КЦ-1» (владелец 19.10: «залей в новую группу всё это под кц»).

Источник — KC-1-pochta.xlsx (лист «Компании»), выжимка kc1-zaliv.json на дропе:
адрес «Письмо: e-mail» (лесенка уже выбрала лучший), дубли адресов убраны.
* НОВЫЙ адрес -> получатель: группа «КЦ-1», сегмент «кц» (направление КЦ),
  ИНН/регион/часовой пояс, контакт и должность из лесенки;
* адрес УЖЕ ЕСТЬ -> только дописываем «КЦ-1» в extra.gruppy, остальное не трогаем;
* компания с настоящим ИНН, которой нет в enrich.companies -> заводим туда
  название, сайт, ОКВЭД, выручку, регион, продукцию (их читает генератор).
Пачками по 200 в одной транзакции. Журнал — _ops/kc1-zaliv.jsonl.
Без --primenit — сухой прогон.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
from sender.regions import region_to_tz  # noqa: E402
try:
    from zona_po_innu import зона_по_inn  # noqa: E402
except Exception:  # noqa: BLE001
    def зона_по_inn(_i):
        return None

ГРУППА = "КЦ-1"
ИСТОЧНИК = "kc-1-pochta"
ПРИМЕНИТЬ = "--primenit" in sys.argv
ФАЙЛ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("fayl=")), r"C:\seostat\drop\drop-storage\kc1-zaliv.json")
ЖУРНАЛ = r"C:\sender\_ops\kc1-zaliv.jsonl"

_д = json.load(io.open(ФАЙЛ, encoding="utf-8"))
# kc1-lesenka.json (владелец 19.10: «для всех всю лесенку добавь, основной = лучший»):
# {"главные": [...как в kc1-zaliv...], "запас": [{inn, email, role, fio, dolzh, url}, ...]}
строки = _д["главные"] if isinstance(_д, dict) else _д
запас = _д.get("запас", []) if isinstance(_д, dict) else []
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
есть = {str(r[0]).lower(): (r[1], r[2]) for r in c.execute("SELECT email, id, extra_json FROM recipients")}
в_обог = {str(r[0]) for r in e.execute("SELECT inn FROM companies")}
кол_обог = {r[1] for r in e.execute("PRAGMA table_info(companies)")}
now = datetime.now(timezone.utc).isoformat()

новые, дописать, обог = [], [], []
сч = Counter()
for z in строки:
    em = z["email"].strip().lower()
    if em in есть:
        rid, ex = есть[em]
        x = json.loads(ex or "{}")
        гр = list(x.get("gruppy") or [])
        if ГРУППА in гр:
            сч["адрес уже в группе"] += 1
            continue
        x["gruppy"] = гр + [ГРУППА]
        x.setdefault("kc1", {"stupen": z.get("stupen"), "segment_kc1": z.get("segment")})
        дописать.append((json.dumps(x, ensure_ascii=False), now, rid))
        сч["адрес уже был — дописана группа"] += 1
    else:
        tz = (зона_по_inn(z["inn"]) if z.get("inn") else None) or region_to_tz(z.get("region")) or "Europe/Moscow"
        extra = {"gruppy": [ГРУППА], "istochnik": "KC-1-pochta.xlsx", "otrasl": z.get("segment"),
                 "stupen": z.get("stupen"), "dolzhnost": z.get("dolzhnost"), "site": z.get("site"),
                 "revenue_rub": z.get("revenue"), "holding": z.get("holding"),
                 "inn_raw": None if z.get("inn") else z.get("inn_raw"),
                 "target_division": "kc", "target_division_istochnik": "база КЦ-1, владелец 19.10"}
        новые.append((em, em.split("@", 1)[1], z.get("inn"), z.get("name"), z.get("okved"), "кц",
                       z.get("fio"), ИСТОЧНИК, z.get("region"), tz,
                       json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False), now, now))
        сч["новый получатель"] += 1
    if z.get("inn") and z["inn"] not in в_обог:
        в_обог.add(z["inn"])
        поля = {"inn": z["inn"], "name": z.get("name"), "site": z.get("site"), "okved": z.get("okved"),
                "revenue_rub": z.get("revenue"), "region": z.get("region"),
                "activity": "; ".join(x for x in (z.get("produkciya"), z.get("oborud")) if x) or None}
        обог.append({k: v for k, v in поля.items() if v and k in кол_обог})
        сч["компания в обогащение"] += 1
кол_адр = {r[1] for r in e.execute("PRAGMA table_info(emails)")}
есть_адр = {(str(r[0]), str(r[1]).lower()) for r in e.execute("SELECT inn, email FROM emails")}
запас_нов = []
for a in запас:
    ключ = (str(a["inn"]), a["email"])
    if ключ in есть_адр:
        continue
    есть_адр.add(ключ)
    п = {"inn": a["inn"], "email": a["email"], "role": (a.get("role") or "") + (" | " + a["dolzh"] if a.get("dolzh") else ""),
         "source": "kc-1-pochta", "source_url": a.get("url")}
    запас_нов.append({k: v for k, v in п.items() if v and k in кол_адр})
сч["запасной адрес лесенки в обогащение"] = len(запас_нов)
print("строк в файле:", len(строки))
for k, v in сч.most_common():
    print("   %-36s %6d" % (k, v))
if not ПРИМЕНИТЬ:
    print("СУХОЙ ПРОГОН. Писать — --primenit")
    sys.exit()


def пачкой(conn, работа):
    for _ in range(40):
        try:
            conn.execute("BEGIN IMMEDIATE")
            работа()
            conn.execute("COMMIT")
            return True
        except sqlite3.OperationalError as ex:
            try:
                conn.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
            if "locked" in str(ex) or "busy" in str(ex):
                time.sleep(3)
                continue
            raise
    return False


c.isolation_level = None
e.isolation_level = None
ж = io.open(ЖУРНАЛ, "a", encoding="utf-8")
for i in range(0, len(новые), 200):
    кус = новые[i:i + 200]
    пачкой(c, lambda: c.executemany(
        "INSERT OR IGNORE INTO recipients (email, domain, inn, company_name, okved, segment, contact_name, source,"
        " region, tz, extra_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", кус))
    for r in кус:
        ж.write(json.dumps({"что": "новый", "email": r[0]}, ensure_ascii=False) + "\n")
for i in range(0, len(дописать), 200):
    кус = дописать[i:i + 200]
    пачкой(c, lambda: c.executemany("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?", кус))
    for r in кус:
        ж.write(json.dumps({"что": "группа", "id": r[2]}) + "\n")
for i in range(0, len(обог), 200):
    кус = обог[i:i + 200]

    def _о():
        for п in кус:
            e.execute("INSERT OR IGNORE INTO companies (%s) VALUES (%s)" % (",".join(п), ",".join("?" * len(п))),
                      list(п.values()))
    пачкой(e, _о)
for i in range(0, len(запас_нов), 300):
    кус = запас_нов[i:i + 300]

    def _з():
        for п in кус:
            e.execute("INSERT OR IGNORE INTO emails (%s) VALUES (%s)" % (",".join(п), ",".join("?" * len(п))),
                      list(п.values()))
    пачкой(e, _з)
ж.flush()
os.fsync(ж.fileno())
ж.close()
print("ПРИМЕНЕНО. в группе «%s» теперь:" % ГРУППА,
      c.execute("SELECT COUNT(*) FROM recipients WHERE extra_json LIKE ?", ("%" + ГРУППА + "%",)).fetchone()[0])
