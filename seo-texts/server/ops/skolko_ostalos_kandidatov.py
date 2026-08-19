# -*- coding: utf-8 -*-
"""Есть ли ещё кому писать: перепись кандидатов по направлениям и почтовикам.

Владелец спросил прямо: есть на чём генерировать или остались одни
корпораты. Отвечаем тем же отбором, каким идёт генерация (заслон
подтверждения, дубли по ИНН, «письмо уже есть», исчерпанные попытки), но
БЕЗ вызовов модели: гейт адресата тут не спрашиваем — он платный, а на
вопрос «есть ли сырьё» влияет процентом, а не наличием.

Считаем в разрезе: направление (кц/мейер) x почтовик (публичный/свой).
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import target_division                           # noqa: E402
from sender.ai_quota import build_ai_quota                             # noqa: E402
from sender.config import Config                                       # noqa: E402
from sender.confirm import ConfirmSend                                 # noqa: E402
from sender.store import Store                                         # noqa: E402
from sender.suppression import Suppression                             # noqa: E402

ГРУППА = sys.argv[1] if len(sys.argv) > 1 else "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
СВОЙ_СЕРВЕР = ("other", "unknown", "")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))

сделано_инн, попыток_инн = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                              # noqa: BLE001
            continue
        inn = str(z.get("inn") or "")
        if not inn:
            continue
        if z.get("этап") == "отмена_попытки":
            попыток_инн[inn] = max(0, попыток_инн[inn] - 1)
            continue
        if z.get("этап") != "итог":
            попыток_инн[inn] += 1
        if z.get("ок") or z.get("тело"):
            сделано_инн.add(inn)
print(f"в журнале генерации: письмо есть у {len(сделано_инн)} ИНН")

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print(f"строк в группе «{ГРУППА}»: {len(в_группе)}")

счёт = Counter()
итог = Counter()
видели = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["строки без карточки"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if inn in видели:
        счёт["дубль фирмы"] += 1
        continue
    видели.add(inn)
    if inn in сделано_инн:
        счёт["письмо уже есть"] += 1
        continue
    if попыток_инн[inn] >= 3:
        счёт["исчерпал 3 попытки"] += 1
        continue
    причина = cs._guard(inn=inn, email=email)
    if причина:
        счёт[f"заслон: {причина.split(':')[0]}"] += 1
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    почта = "свой сервер" if mx in СВОЙ_СЕРВЕР else f"публичный ({mx})"
    напр = "?"
    try:
        _req = q._request(rec)
        напр = str(_req.get("target_division") or "")
        if напр not in ("kc", "meyer"):
            напр, _ = target_division(_req, default="kc")
    except Exception:                                                  # noqa: BLE001
        счёт["направление не посчиталось"] += 1
        напр = "?"
    итог[(напр, "свой" if mx in СВОЙ_СЕРВЕР else "публичный")] += 1
    счёт[f"ГОДЕН: {напр} / {почта.split(' (')[0]}"] += 1

print("\n== отсев ==")
for k, v in счёт.most_common():
    if not k.startswith("ГОДЕН"):
        print(f"  {v:>6}  {k}")

print("\n== СЫРЬЁ ДЛЯ ГЕНЕРАЦИИ ==")
print(f"  {'направление':<12} {'публичная почта':>16} {'свой сервер':>14}")
for напр in ("kc", "meyer", "?"):
    пуб = итог[(напр, "публичный")]
    свой = итог[(напр, "свой")]
    if пуб or свой:
        имя = {"kc": "КЦ", "meyer": "Meyer"}.get(напр, напр)
        print(f"  {имя:<12} {пуб:>16} {свой:>14}")
всего_пуб = sum(v for (н, т), v in итог.items() if т == "публичный")
всего_свой = sum(v for (н, т), v in итог.items() if т == "свой")
print(f"  {'ИТОГО':<12} {всего_пуб:>16} {всего_свой:>14}")
