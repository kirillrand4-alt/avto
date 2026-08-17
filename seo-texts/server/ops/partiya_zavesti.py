# -*- coding: utf-8 -*-
"""Завести партию кандидатов (полный паспорт + почта ЛПР/закупщика) в панель.

Задача владельца 17.08: 935 писем по чистым адресам тем, кому мы не писали.
803 кандидата из 935 живут только в обогащении - здесь их заводим.

Что делает:
  1. собирает кандидатов из enrich.db (паспорт вес>=8 + почта нужной роли);
  2. дедуп по ИНН, а не по строке: 169 лишних строк в панели уже есть, и
     без этого одна фирма получит два письма на два адреса;
  3. выбирает лучший контакт по приоритету ролей, отбрасывая убитых пробой;
  4. upsert получателя с ИНН/регионом/таймзоной (tz нужна окну 9-11 по
     МЕСТНОМУ времени при автоотправке) и меткой группы;
  5. проверяет каждого штатным заслоном подтверждения (стоп-лист, мёртвый
     адрес, контакт <90 дней) - под заслоном в группу не берём.

Сухой прогон по умолчанию; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.confirm import ConfirmSend                        # noqa: E402
from sender.dtos import RecipientIn                           # noqa: E402
from sender.regions import region_to_tz                       # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.suppression import Suppression                    # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\partiya-935-zavod.jsonl"
ENRICH = r"C:\sender\enrich.db"
ВЕС_МИН = 8

# Приоритет контакта: сначала тот, кто решает по нашей теме, потом закупки,
# потом руководство. Внутри роли выигрывает адрес с чистым вердиктом пробы.
ПРИОРИТЕТ = ["гл.инженер", "техдиректор", "гл.механик", "гл.энергетик",
             "гл.технолог", "нач.производства", "нач.цеха", "гл.конструктор",
             "АСУ/КИПиА", "техконтакт", "инженер (не главный)",
             "снабжение/закупки", "закупки", "директор"]
МЁРТВЫЕ = {"нет ящика", "нет MX"}
КЛЮЧИ = ("продукция", "сырьё", "упаковка_фасовка", "мощности",
         "контроль_качества", "экспорт", "оборудование_линии",
         "география_поставок", "масштаб", "год_основания")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
ex = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True)
ex.row_factory = sqlite3.Row


def вес(f: dict) -> int:
    n = 0
    for k in КЛЮЧИ:
        v = f.get(k)
        n += len(v) if isinstance(v, (list, tuple)) else (1 if v else 0)
    return n


паспорта = {}
for r in ex.execute("SELECT inn, facts_json FROM site_facts"):
    try:
        f = json.loads(r["facts_json"] or "{}")
    except Exception:
        continue
    if isinstance(f, dict) and вес(f) >= ВЕС_МИН:
        паспорта[str(r["inn"])] = вес(f)

контакты = {}
for r in ex.execute(
        "SELECT inn, email, role, person, probe_verdict FROM emails "
        "WHERE email IS NOT NULL AND email<>''"):
    роль = str(r["role"] or "").strip()
    if роль not in ПРИОРИТЕТ:
        continue
    контакты.setdefault(str(r["inn"]), []).append({
        "email": str(r["email"]).strip().lower(), "role": роль,
        "person": str(r["person"] or "").strip(),
        "verdict": str(r["probe_verdict"] or "")})


def лучший(лист):
    живые = [c for c in лист if c["verdict"] not in МЁРТВЫЕ]
    if не_пусто := [c for c in живые if c["verdict"] == "есть"]:
        живые = не_пусто
    живые.sort(key=lambda c: ПРИОРИТЕТ.index(c["role"]))
    return живые[0] if живые else None


фирмы = {}
for r in ex.execute(
        "SELECT inn, name, short_name, region, okved, activity, site, "
        "division, is_competitor, verified FROM companies"):
    фирмы[str(r["inn"])] = dict(r)

# Уже заведённые - по ИНН и по адресу. Нужны ОБА среза: у компании в панели
# может быть несколько строк с разными адресами (169 таких лишних строк), и
# нужный нам контакт нередко уже лежит на СОСЕДНЕЙ строке той же фирмы.
# Переименовывать при этом нельзя - email уникален, и UPDATE падает.
есть_в_панели = {}
строки_инн = {}
адрес_занят = {}
with store._lock:
    for row in store._conn.execute(
            "SELECT id, COALESCE(inn,''), COALESCE(email,'') FROM recipients"):
        rid, d, em = int(row[0]), str(row[1]), str(row[2]).strip().lower()
        d = "".join(c for c in d if c.isdigit())
        if em:
            адрес_занят[em] = rid
        if d:
            есть_в_панели.setdefault(d, rid)
            строки_инн.setdefault(d, []).append((rid, em))

шаг = Counter()
к_заводу = []
for inn, в in sorted(паспорта.items(), key=lambda kv: -kv[1]):
    шаг["паспорт полный"] += 1
    c = лучший(контакты.get(inn) or [])
    if not c:
        continue
    шаг["+ живой контакт нужной роли"] += 1
    ф = фирмы.get(inn) or {}
    # Конкурентам не пишем: их ИНН помечены в обогащении отдельным полем, и
    # это дешевле поймать здесь, чем объяснять потом.
    if int(ф.get("is_competitor") or 0):
        шаг["- конкурент"] += 1
        continue
    if cs._guard(inn=inn, email=c["email"]):
        шаг["- под заслоном"] += 1
        continue
    шаг["ЧИСТЫХ"] += 1
    к_заводу.append((inn, в, c, ф))

print(f"режим: {'ПРИМЕНЯЮ' if ПРИМЕНИТЬ else 'сухой прогон'}")
for k in ("паспорт полный", "+ живой контакт нужной роли", "- конкурент",
          "- под заслоном", "ЧИСТЫХ"):
    print(f"  {k:<30} {шаг[k]}")
новых = sum(1 for inn, *_ in к_заводу if inn not in есть_в_панели)
print(f"  {'из них новых для панели':<30} {новых}")
print(f"  {'уже есть строкой':<30} {len(к_заводу) - новых}")

print("\nроли выбранных контактов:",
      dict(Counter(c["role"] for _i, _v, c, _f in к_заводу)))
print("вердикт пробы у выбранных:",
      dict(Counter(c["verdict"] or "(не проверен)" for _i, _v, c, _f in к_заводу)))

if not ПРИМЕНИТЬ:
    print("\nсухой прогон: ничего не менял")
    for inn, в, c, f in к_заводу[:8]:
        print(f"  {inn:<13} вес {в:<3} {c['role']:<20} {c['email'][:32]:<34}"
              f" {str(f.get('short_name') or f.get('name'))[:30]}")
    raise SystemExit(0)

заведено = обновлено = 0
адрес_сменён = []
конфликт_адреса = []
for inn, в, c, f in к_заводу:
    имя = str(f.get("short_name") or f.get("name") or "").strip()
    регион = str(f.get("region") or "").strip()
    tz = region_to_tz(регион) or "Europe/Moscow"
    дом = c["email"].split("@")[-1]
    было = inn in есть_в_панели
    # ГЛАВНОЕ: upsert ключуется по EMAIL, а не по ИНН. Для компании, которая
    # уже в панели под другим адресом, он завёл бы ВТОРУЮ строку - ровно те
    # дубли, из-за которых «Богатые карточки» показывали 48 строк на 43
    # фирмы, и одна фирма получила бы два письма на два адреса. Поэтому:
    # компания есть - берём её строку и при нужде правим адрес на месте.
    if было:
        свои = строки_инн.get(inn) or []
        уже = next((r for r, em in свои if em == c["email"]), None)
        if уже is not None:
            # нужный адрес уже есть строкой этой же фирмы - берём её
            rid = уже
        else:
            rid = есть_в_панели[inn]
            чужой = адрес_занят.get(c["email"])
            if чужой is not None and чужой != rid:
                # адрес занят строкой ДРУГОЙ компании - не трогаем ни ту, ни
                # эту, пишем по тому адресу, что уже стоит у нашей
                конфликт_адреса.append((inn, c["email"], чужой))
            else:
                стар = store.get_recipient(rid)
                старый = str(getattr(стар, "email", "") or "").strip().lower()
                if старый != c["email"]:
                    with store.transaction() as conn:
                        conn.execute(
                            "UPDATE recipients SET email=?, domain=?,"
                            " contact_name=?, tz=COALESCE(tz,?), updated_at=?"
                            " WHERE id=?",
                            (c["email"], дом, c["person"] or None, tz,
                             time.strftime("%Y-%m-%dT%H:%M:%S"), rid))
                    адрес_занят.pop(старый, None)
                    адрес_занят[c["email"]] = rid
                    адрес_сменён.append((inn, старый, c["email"], c["role"]))
    else:
        if c["email"] in адрес_занят:
            конфликт_адреса.append((inn, c["email"], адрес_занят[c["email"]]))
            continue
        rid = store.upsert_recipient(RecipientIn(
            email=c["email"], domain=дом, inn=inn, company_name=имя or None,
            okved=str(f.get("okved") or "") or None,
            contact_name=c["person"] or None, region=регион or None, tz=tz,
            source="партия-935", extra={}))
    # группа и служебные метки - отдельным полем, чтобы не затирать чужое
    rec = store.get_recipient(rid)
    e = getattr(rec, "extra", None)
    if isinstance(e, str):
        try:
            e = json.loads(e)
        except Exception:
            e = {}
    e = dict(e or {})
    гр = [str(g) for g in (e.get("gruppy") or [])]
    if ГРУППА not in гр:
        гр.append(ГРУППА)
    e["gruppy"] = гр
    e["ves_pasporta"] = в
    e["rol_kontakta"] = c["role"]
    if f.get("verified"):
        e["verified"] = str(f["verified"])
    if f.get("activity"):
        e["activity"] = str(f["activity"])
    with store.transaction() as conn:
        conn.execute("UPDATE recipients SET extra_json=? WHERE id=?",
                     (json.dumps(e, ensure_ascii=False), rid))
    заведено += 0 if было else 1
    обновлено += 1 if было else 0
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"inn": inn, "recipient_id": rid, "вес": в,
                             "email": c["email"], "роль": c["role"],
                             "новый": not было, "ts": int(time.time())},
                            ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

print(f"\nзаведено новых: {заведено} | обновлено существующих: {обновлено}")
print(f"адрес переставлен на контакт с ролью: {len(адрес_сменён)}")
print(f"адрес занят другой компанией (не трогал): {len(конфликт_адреса)}")
for inn, ст, нов, роль in адрес_сменён[:10]:
    print(f"  {inn:<13} {ст[:30]:<32} -> {нов[:30]:<32} ({роль})")
группы = store.recipient_groups().get("по_id") or {}
в_гр = [rid for rid, gr in группы.items() if ГРУППА in gr]
print(f"в группе «{ГРУППА}»: {len(в_гр)}")
