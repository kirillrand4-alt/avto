# -*- coding: utf-8 -*-
"""Сколько в «Партии 935» осталось необработанных — дешёвыми фильтрами.

Повторяет отбор partiya_gen.py до платных шагов: группа, ИНН+почта,
приговор пробы, предпросев, дубль фирмы, резюм по журналу. Гейт покупателя
и предклассификатор направления НЕ трогаем — они стоят денег.
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.ai_letter import target_division                  # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ГРУППА = "Партия 935"
СВОЙ_СЕРВЕР = ("other", "unknown", "")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

сделано = set()
строк = 0
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8"):
        строк += 1
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if (z.get("ок") or z.get("тело")) and z.get("inn"):
            сделано.add(str(z["inn"]))
print("журнал: %d строк, фирм с готовым текстом: %d" % (строк, len(сделано)))

мёртвые = set()
try:
    from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА          # noqa: E402
    with store._lock:
        for (а,) in store._conn.execute(
                "SELECT email FROM addr_probe WHERE verdict IN (?,?)",
                (НЕТ_ЯЩИКА, НЕТ_MX)).fetchall():
            if а:
                мёртвые.add(str(а).strip().lower())
except Exception as e:                                        # noqa: BLE001
    print("приговоры не прочитались: %s" % str(e)[:80])
print("приговоров «мёртв»: %d" % len(мёртвые))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print("строк в группе «%s»: %d" % (ГРУППА, len(в_группе)))

счёт = Counter()
видели, живые_kc, живые_meyer, корп_kc = set(), 0, 0, 0
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["нет карточки"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if email in мёртвые:
        счёт["приговор пробы"] += 1
        continue
    доп = getattr(rec, "extra", None) or {}
    if str(доп.get("ne_nash_ni_odnomu") or "").strip():
        счёт["предпросев: не наш"] += 1
        continue
    if inn in видели:
        счёт["дубль фирмы"] += 1
        continue
    видели.add(inn)
    if inn in сделано:
        счёт["письмо уже есть"] += 1
        continue
    лёгкий = {"company_name": getattr(rec, "company_name", "") or "",
              "okved": getattr(rec, "okved", "") or "",
              "activity": str(доп.get("activity") or ""),
              "extra": доп}
    d, _ = target_division(лёгкий, default="kc")
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    свой = mx in СВОЙ_СЕРВЕР
    if d == "meyer":
        живые_meyer += 1
    else:
        if свой:
            корп_kc += 1
        else:
            живые_kc += 1

print("\n=== ОТСЕВ ===")
for п, n in счёт.most_common():
    print("   %-28s %6d" % (п, n))

print("\n=== ИТОГ ===")
print("свободных фирм в группе: %d" % (живые_kc + корп_kc + живые_meyer))
print("   из них по лёгкой прикидке направления:")
print("      КЦ на публичной почте (пойдут в прогон «kc 1»): %d" % живые_kc)
print("      КЦ на своём почтовом сервере (режим 1 их пропустит): %d" % корп_kc)
print("      Meyer: %d" % живые_meyer)
print("хватает ли на 400 писем КЦ: %s"
      % ("да" if живые_kc >= 400 else "НЕТ, только %d" % живые_kc))
print("(направление тут прикинуто дёшево; в прогоне его считает та же")
print(" цепочка, но по собранному запросу, и часть писем переедет в Meyer)")
