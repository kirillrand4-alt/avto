# -*- coding: utf-8 -*-
"""Завести группу получателей meyer-v30 под три критерия владельца.

  1) паспорт сайта с хотя бы одним полем-ФАКТОМ (служебные поля не в счёт)
  2) почта с сайта паспорта ЛИБО её домен совпадает с доменом паспорта
  3) выручка >= 30 млн

Имя группы латиницей намеренно: кириллица бьётся кодировкой по дороге через
PowerShell Start-Process (комментарий в partiya_gen, строки 75-79).

Пишем ТОЛЬКО ключ 'gruppy' внутри extra_json, остальные ключи сохраняем.
upsert_recipient НЕ используем: он заменяет extra целиком и стирает паспорт.
Без аргумента primenit ничего не меняет.
"""
import json
import sqlite3
import sys

ИМЯ = "meyer-v30"
ПОРОГ = 30_000_000
ПРИМЕНИТЬ = "primenit" in sys.argv

СУТЬ = {"продукция", "упаковка_фасовка", "сырьё", "мощности", "контроль_качества",
        "экспорт", "оборудование_линии", "клиенты", "год_основания",
        "география_поставок", "масштаб", "расширение", "газы", "энергохозяйство",
        "новости"}


def непусто(v):
    return v not in (None, "", [], {}, "нет")


def норм(d):
    d = str(d or "").strip().lower()
    for п in ("https://", "http://"):
        if d.startswith(п):
            d = d[len(п):]
    d = d.split("/")[0].split("?")[0].split(":")[0]
    return (d[4:] if d.startswith("www.") else d).strip(". ")


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
пасп = {}
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    пасп[str(р["inn"])] = (норм(р["site"]),
                           sum(1 for k, v in f.items() if k in СУТЬ and непусто(v)))
выр = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выр[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass
ист = {}
for таб, кол in (("emails", "source_url"), ("email_sources", "url")):
    for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол, таб)):
        d = норм(р["u"])
        if d:
            ист.setdefault((str(р["inn"]), str(р["email"] or "").lower()), set()).add(d)

s = sqlite3.connect(r"C:\sender\sender.db")
s.row_factory = sqlite3.Row
кандидаты = []
инн = set()
for р in s.execute("SELECT id, inn, email, domain, extra_json FROM recipients"
                   " WHERE segment='meyer'"):
    i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    p = пасп.get(i)
    if not p:
        continue
    сайт, фактов = p
    if фактов < 1:
        continue
    if not (сайт and (dom == сайт or сайт in ист.get((i, em), set()))):
        continue
    v = выр.get(i)
    # Критерий владельца: выручка от 30 млн ЛИБО неизвестна. Ровно 0 в
    # companies означает «нет данных» (таких 56881 из 166620), поэтому ноль
    # приравниваем к неизвестной, а не к нулевому обороту.
    if not (v is None or v == 0 or v >= ПОРОГ):
        continue
    кандидаты.append((р["id"], р["extra_json"]))
    инн.add(i)

print("=== ОТБОР В ГРУППУ «%s» ===" % ИМЯ)
print("  адресов подошло : %d" % len(кандидаты))
print("  уникальных ИНН  : %d" % len(инн))

добавлено = уже = ошибок = 0
if ПРИМЕНИТЬ:
    cur = s.cursor()
    for rid, ej in кандидаты:
        try:
            d = json.loads(ej) if ej else {}
            if not isinstance(d, dict):
                d = {}
            гр = d.get("gruppy")
            гр = list(гр) if isinstance(гр, list) else ([гр] if гр else [])
            if ИМЯ in гр:
                уже += 1
                continue
            гр.append(ИМЯ)
            d["gruppy"] = гр
            cur.execute("UPDATE recipients SET extra_json=? WHERE id=?",
                        (json.dumps(d, ensure_ascii=False), rid))
            добавлено += 1
        except Exception as ex:
            ошибок += 1
            if ошибок < 4:
                print("  ОШИБКА на id=%s: %s" % (rid, str(ex)[:80]))
    s.commit()

    # проверка боевой функцией панели
    sys.path.insert(0, r"C:\sender")
    from sender.config import Config    # noqa: E402
    from sender.store import Store      # noqa: E402
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    по_id = store.recipient_groups().get("по_id") or {}
    видит = sum(1 for gr in по_id.values() if ИМЯ in (gr or []))
    print("\n=== ПРОВЕРКА ===")
    print("  панель видит в группе «%s»: %d получателей" % (ИМЯ, видит))

print("\n=== ИТОГ ===")
print("  адресов в отборе: %d, компаний: %d" % (len(кандидаты), len(инн)))
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО: добавлено %d, уже было %d, ошибок %d"
                       % (добавлено, уже, ошибок) if ПРИМЕНИТЬ
                       else "показ без изменений (аргумент primenit)"))
