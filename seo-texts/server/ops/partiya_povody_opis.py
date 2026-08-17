# -*- coding: utf-8 -*-
"""Опись новостных поводов группы: у кого какой повод и чем он подтверждён.

Владелец 17.08 показал Обуховский мясокомбинат (obuhmk.ru, Старый Оскол,
свинина), которому подставили новость про мусорный комплекс «Обухово» ГК
«Первый Спецтранс» в Петербурге. Это тёзка, а не их событие.

Здесь НИЧЕГО не меняем - только снимаем опись: для каждой компании группы
спрашиваем ровно тот повод, который взяла бы генерация (_digest с именем),
и выкладываем всё, на чём он держится: имя в тексте, inn_conf, ссылку.
Дальше поводы вычитываются глазами и провайдером, а снимаются проставлением
suspect=1 в signals - штатным карантином.

Результат durable: JSON на сервере, а не только в выводе.
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ГРУППА = "Партия 935"
ВЫХОД = r"C:\sender\_ops\povody-opis.json"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

видели_инн = set()
опись, счёт = [], Counter()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    имя = str(getattr(rec, "company_name", "") or "")
    if not inn or inn in видели_инн:
        continue
    видели_инн.add(inn)
    try:
        d = q._digest(inn, имя) or {}
    except Exception as ex:                                    # noqa: BLE001
        счёт[f"дайджест упал: {str(ex)[:40]}"] += 1
        continue
    if not d:
        счёт["повода нет"] += 1
        continue
    счёт["ПОВОД ЕСТЬ"] += 1
    строка = {"inn": inn, "имя": имя,
              "сайт": str(getattr(rec, "site", "") or ""),
              "регион": str(getattr(rec, "region", "") or "")}
    # Ключи дайджеста именно такие - news_detail/news_type/news_sum/
    # news_url/digest. Первый заход я спросил event_type/what/sum и получил
    # пустоту, отчего опись показала «имя в тексте: нет» у всех 224 подряд.
    for k in ("news_detail", "news_type", "news_sum", "news_url", "digest"):
        if d.get(k):
            строка[k] = d[k]
    # На чём держится привязка: имя в тексте или доверие матчинга.
    сверка = " ".join(str(строка.get(k) or "")
                      for k in ("news_detail", "news_sum", "news_url",
                                "news_type"))
    строка["имя_в_тексте"] = q._novost_pro_etu_kompaniyu(сверка, имя)
    строка["надёжен_по_inn_conf"] = \
        str(строка.get("inn_conf") or "").lower() == "high"
    опись.append(строка)
    счёт["держится на имени" if строка["имя_в_тексте"]
         else "держится ТОЛЬКО на inn_conf"] += 1

with io.open(ВЫХОД, "w", encoding="utf-8") as f:
    json.dump(опись, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())

print(f"компаний в группе (уникальных ИНН): {len(видели_инн)}")
for k, n in счёт.most_common():
    print(f"  {k:<34} {n}")
print(f"\nопись сохранена: {ВЫХОД} ({len(опись)} поводов)")

print("\nпервые 12 поводов:")
for з in опись[:12]:
    print(f"\n  {з['имя'][:44]}  | {з.get('сайт') or 'сайта нет'}"
          f" | {з.get('регион') or ''}")
    print(f"    имя_в_тексте={з['имя_в_тексте']} "
          f"inn_conf={з.get('inn_conf')!r} накал={з.get('hotness')}")
    for k in ("news_type", "news_detail", "news_sum"):
        if з.get(k):
            print(f"    {k}: {str(з[k])[:170]}")
    if з.get("news_url"):
        print(f"    ссылка: {str(з['news_url'])[:120]}")
