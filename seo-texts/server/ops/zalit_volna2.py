# -*- coding: utf-8 -*-
"""Залить ярус A файла FSA-MEYER-v4-Meyer в группу «ФСА волна 1» (кампания 18)
(владелец 22.10: «Ярус А 1319 мейер запускай»; профиль только ОКВЭД 10/11/01/03,
провалы Meyer 2025–26 — писать). Выжимка volna2-zaliv.json (1124 компании,
новые для панели по ИНН): почта есть, паспорт от 3 полей, не торговля; почта
оформителя деклараций отсечена.
ОТЛИЧИЕ ОТ volna1: ИНН этих компаний в панели нет, значит адрес, который в
панели уже есть, принадлежит ДРУГОЙ компании (общий ящик холдинга, агрогруппы)
— его не берём, идём к следующему кандидату.

Адрес письма: лучший контакт файла -> контакты файла по ступени лесенки ->
адрес из наших баз по лесенке ролей. Кадры/бухгалтерия/«не для письма» — нет.
Получатель: группа «ФСА волна 1», сегмент meyer, target_division meyer; адрес
уже есть — дописываем группу. Компания без строки в enrich.companies — заводим
(название, сайт, ОКВЭД, выручка, регион, продукция + паспорт). Новые адреса
файла — в enrich.emails (source fsa-volna1). Журнал _ops/volna2-zaliv.jsonl.
Без --primenit — счёт."""
import io
import json
import re
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 4

# --gruppa=латиницей: c10 -> «ФСА v4 C проба» (владелец 22.10: «вот этих [ярус C]
# штук 10 писем сделай … посмотрю насколько хороши»)
ГРУППА = {"c10": "ФСА v4 C проба"}.get(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--gruppa=")), ""), "ФСА волна 1")
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|финанс|hr|резюме|не для письма")
# ярус B (владелец 22.10: «B тоже запускай мейер по тем же правилам»):
#   zalit_volna2.py --yarus=B  -> volna2-zaliv-b.json, extra volna=v4-B
ЯРУС = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--yarus=")), "A").upper()
д = json.load(io.open(r"C:\seostat\drop\drop-storage\volna2-zaliv%s.json" % ("" if ЯРУС == "A" else "-" + ЯРУС.lower()),
                      encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
есть_получ = {str(r[0]).lower(): (r[1], r[2]) for r in c.execute("SELECT email, id, extra_json FROM recipients")}
в_обог = {str(r[0]) for r in e.execute("SELECT inn FROM companies")}
кол_c = {r[1] for r in e.execute("PRAGMA table_info(companies)")}
кол_e = {r[1] for r in e.execute("PRAGMA table_info(emails)")}
есть_адр = {(str(r[0]), str(r[1]).lower()) for r in e.execute("SELECT inn, email FROM emails")}
конт = {}
for к in д["cont"]:
    конт.setdefault(к["inn"], []).append(к)
сч = Counter()
новые, дописать, обог, адреса_обог = [], [], [], []
now = time.strftime("%Y-%m-%dT%H:%M:%S")


def годен(адр, роль=""):
    return адр and "@" in адр and адр not in стоп and адр.split("@")[-1] not in стоп and not ПЛОХО.search(str(роль or "")) \
        and проба.get(адр, "") not in ("нет ящика", "нет MX") and адр not in есть_получ


for к in д["comp"]:
    inn = к["inn"]
    кандидаты = []
    if годен(к["best"], ""):
        кандидаты.append((0, к["best"], к.get("best_fio"), к.get("best_dolzh") or "лучший контакт файла"))
    # ступень «никогда» — файл сам запрещает писать на этот контакт
    for x in sorted((x for x in конт.get(inn, []) if str(x.get("step") or "").strip().lower() != "никогда"),
                    key=lambda x: int(re.sub(r"\D", "", str(x.get("step") or "")) or 99)):
        if годен(x["email"], x.get("role")):
            кандидаты.append((1, x["email"], x.get("fio"), x.get("dolzh") or x.get("role")))
    свои = []
    for адр, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
        if годен(адр, роль) and _rol_ball(str(роль or "")) > 1:
            свои.append((-_rol_ball(str(роль or "")), адр, None, роль))
    for _б, адр, fio, роль in sorted(свои):
        кандидаты.append((2, адр, fio, роль))
    if not кандидаты:
        сч["нет годного адреса"] += 1
        continue
    _ист, адр, fio, роль = кандидаты[0]
    сч[("адрес из файла" if _ист < 2 else "адрес из наших баз")] += 1
    extra = {"gruppy": [ГРУППА], "istochnik": "FSA-MEYER-v4-Meyer.xlsx", "volna": "v4-" + ЯРУС, "target_division": "meyer",
             "target_division_istochnik": "ФСА v4 ярус %s, владелец 22.10" % ЯРУС, "dolzhnost": роль, "site": к.get("site"),
             "revenue_rub": к.get("rev"), "pochemu_meyer": к.get("pochemu"), "pasport_fsa": к.get("pasport")}
    if адр in есть_получ:
        rid, ex = есть_получ[адр]
        x = json.loads(ex or "{}")
        if ГРУППА not in (x.get("gruppy") or []):
            x["gruppy"] = list(x.get("gruppy") or []) + [ГРУППА]
            x.setdefault("pasport_fsa", к.get("pasport"))
            дописать.append((json.dumps(x, ensure_ascii=False), now, rid))
        сч["адрес уже в панели — дописана группа"] += 1
    else:
        новые.append((адр, адр.split("@")[-1], inn, к["name"], к["okved"], "meyer", fio, "fsa-v4", к.get("region"),
                       "Europe/Moscow", json.dumps({k: v for k, v in extra.items() if v}, ensure_ascii=False), now, now))
        сч["новый получатель"] += 1
    if inn not in в_обог:
        в_обог.add(inn)
        п = к.get("pasport") or {}
        поля = {"inn": inn, "name": к["name"], "site": к.get("site"), "okved": к["okved"], "revenue_rub": к.get("rev"),
                "region": к.get("region"), "activity": "; ".join(str(v) for v in (п.get("продукция"), п.get("оборудование и линии")) if v) or None}
        обог.append({k: v for k, v in поля.items() if v and k in кол_c})
        сч["компания в обогащение"] += 1
    for x in конт.get(inn, []):
        if (inn, x["email"]) not in есть_адр and "@" in x["email"]:
            есть_адр.add((inn, x["email"]))
            п = {"inn": inn, "email": x["email"], "role": (x.get("role") or "") + (" | " + x["dolzh"] if x.get("dolzh") else ""),
                 "source": "fsa-v4"}
            адреса_обог.append({k: v for k, v in п.items() if v and k in кол_e})
print("компаний в выжимке:", len(д["comp"]))
for k, v in сч.most_common():
    print("  %-40s %4d" % (k, v))
print("адресов файла в обогащение:", len(адреса_обог))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
ж = io.open(r"C:\sender\_ops\volna2-zaliv.jsonl", "a", encoding="utf-8")
with c:
    c.executemany("INSERT OR IGNORE INTO recipients (email, domain, inn, company_name, okved, segment, contact_name, source, region, tz,"
                  " extra_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", новые)
    c.executemany("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?", дописать)
with e:
    for п in обог:
        e.execute("INSERT OR IGNORE INTO companies (%s) VALUES (%s)" % (",".join(п), ",".join("?" * len(п))), list(п.values()))
    for п in адреса_обог:
        e.execute("INSERT OR IGNORE INTO emails (%s) VALUES (%s)" % (",".join(п), ",".join("?" * len(п))), list(п.values()))
for r in новые:
    ж.write(json.dumps({"что": "новый", "email": r[0], "inn": r[2]}, ensure_ascii=False) + "\n")
for r in дописать:
    ж.write(json.dumps({"что": "группа", "id": r[2]}) + "\n")
ж.close()
print("ПРИМЕНЕНО. В группе «%s»:" % ГРУППА,
      c.execute("SELECT COUNT(*) FROM recipients WHERE extra_json LIKE ?", ("%" + ГРУППА + "%",)).fetchone()[0])
