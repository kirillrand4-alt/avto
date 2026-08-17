# -*- coding: utf-8 -*-
"""Что реально приедет в промпт письма: гоняем ai_quota._request на выборке.

Прошлый замер (ops/partiya_gotovnost_generacii.py) честно показал воронку,
но по полям карточки соврал нулями: activity, роль ящика и направление не
лежат в строке получателя вовсе - их собирает _request из карточки
обогащения. Ноль там означал «я смотрел не туда».

Здесь зовём ТОТ ЖЕ _request, что и генератор, на случайной выборке готовых
получателей и смотрим, с чем письмо пойдёт к модели: направление, профиль
деятельности, роль ящика, новостной повод, боль, идея захода.

Выборка, а не вся партия: _request ходит в карточку и новости, на 5 500
строк это часы. Число берём из аргумента.

    python zapusk_svoego_skripta.py ops/partiya_zapros_polnota.py 300
"""
import io
import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ГРУППА = "Партия 935"
ИМЯ = "ZAPROS-POLNOTA.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 300

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

# Берём КАЖДОГО N-го, а не первых подряд: первые - это старая часть партии,
# и по ней о новых компаниях ничего не узнаешь.
шаг = max(1, len(в_группе) // max(1, СКОЛЬКО * 2))
кандидаты = в_группе[::шаг]

счёт = Counter()
примеры = []
разобрано = 0
видели = set()
for rid in кандидаты:
    if разобрано >= СКОЛЬКО:
        break
    r = store.get_recipient(rid)
    if not r:
        continue
    inn = "".join(c for c in str(getattr(r, "inn", "") or "") if c.isdigit())
    email = str(getattr(r, "email", "") or "").strip().lower()
    if not inn or not email or inn in видели:
        continue
    видели.add(inn)
    if cs._guard(inn=inn, email=email):
        continue
    try:
        req = q._request(r)
    except Exception as ex:                                     # noqa: BLE001
        счёт["_request упал"] += 1
        if len(примеры) < 6:
            примеры.append(f"СБОЙ {getattr(r, 'company_name', '')}: "
                           f"{type(ex).__name__} {str(ex)[:90]}")
        continue
    разобрано += 1
    ex_ = req.get("extra") or {}
    напр = str(req.get("target_division") or "")
    счёт["всего разобрано"] += 1
    счёт[f"направление: {напр or 'НЕ ОПРЕДЕЛЕНО (решит цепочка при генерации)'}"] += 1
    счёт["есть профиль деятельности"] += bool(str(req.get("activity") or "").strip())
    счёт["есть ОКВЭД"] += bool(str(req.get("okved") or "").strip())
    счёт["есть роль ящика"] += bool(str(ex_.get("role") or "").strip())
    счёт["есть новостной повод"] += bool(str(req.get("_digest") or "").strip())
    счёт["есть боль/задача"] += bool(str(ex_.get("bol") or ex_.get("боль")
                                         or "").strip())
    счёт["есть имя контакта"] += bool(str(req.get("contact_name") or "").strip())
    счёт["есть город/регион"] += bool(str(ex_.get("city") or "").strip())
    счёт["НЕЧЕГО ПИСАТЬ: ни профиля, ни ОКВЭДа, ни новости"] += not (
        str(req.get("activity") or "").strip()
        or str(req.get("okved") or "").strip()
        or str(req.get("_digest") or "").strip())
    if len(примеры) < 8:
        примеры.append(
            f"{req.get('company_name')} | напр={напр or '-'} | "
            f"ОКВЭД={str(req.get('okved') or '-')[:34]} | "
            f"профиль={'есть' if req.get('activity') else 'нет'} | "
            f"роль={ex_.get('role') or '-'} | "
            f"новость={'есть' if req.get('_digest') else 'нет'}")

С = [f"# Что доедет в промпт письма (выборка {разобрано} компаний)", "",
     f"Звали ai_quota._request - тот же вызов, что делает генератор.", ""]
for k, n in счёт.most_common():
    доля = f" ({100.0 * n / max(1, разобрано):.0f}%)" if k != "всего разобрано" else ""
    С.append(f"- {k}: **{n}**{доля}")
С += ["", "## Примеры строк", ""]
С += [f"- {s}" for s in примеры]

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

for k, n in счёт.most_common():
    print(f"  {k:<58} {n}")
