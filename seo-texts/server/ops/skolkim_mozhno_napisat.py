# -*- coding: utf-8 -*-
"""Скольким из группы мы реально можем написать: воронка по ситам.

Владелец 24.08: «ещё в группе 12858 компаний, скольким из них мы можем
написать письмо?». Число в группе — это строки получателей, а не
адресаты: одна фирма бывает заведена несколькими адресами, часть уже
получила письмо, часть отсеют заслоны.

Считаем ровно теми ситами, что стоят в partiya_gen, и в том же порядке —
иначе цифра будет красивой, но неверной. Ничего не генерируем и не
пишем: только счёт.

Порядок сит:
  1 нет карточки получателя
  2 нет ИНН или почты
  3 приговор пробы: адрес мёртв
  4 дубль строки той же фирмы
  5 письмо уже есть
  6 исчерпал три попытки
  7 заслоны: отписка, 90 дней, недоставимость
  8 корпоративный почтовый сервер (режим «без корпоративных»)
  9 минус-класс по ОКВЭД (медицина и прочее)
 10 гейт адресата: уже осуждён как «не покупатель»
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.config import Config                               # noqa: E402
from sender.confirm import ConfirmSend                         # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.suppression import Suppression                     # noqa: E402
from sender.target_gate import минус_класс                     # noqa: E402

ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
СВОЙ_СЕРВЕР = ("other", "unknown", "")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

# --- кто уже отработан, по журналу -------------------------------------- #
сделано_инн, попыток = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            з = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        инн = "".join(ч for ч in str(з.get("inn") or "") if ч.isdigit())
        if not инн:
            continue
        попыток[инн] += 1
        if з.get("ок") or з.get("тело"):
            сделано_инн.add(инн)
print("журнал: отработанных ИНН %d" % len(сделано_инн))

# --- приговоры проб ------------------------------------------------------ #
мёртвые = set()
try:
    from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА
    with store._lock:
        for (а,) in store._conn.execute(
                "SELECT email FROM addr_probe WHERE verdict IN (?, ?)",
                (НЕТ_ЯЩИКА, НЕТ_MX)).fetchall():
            а = str(а or "").strip().lower()
            if а:
                мёртвые.add(а)
except Exception as e:                                         # noqa: BLE001
    print("приговоры не прочитались:", str(e)[:70])
print("приговоров «мёртв»: %d" % len(мёртвые))

# --- вердикты гейта ------------------------------------------------------ #
не_покупатели = set()
try:
    with store._lock:
        for (и,) in store._conn.execute(
                "SELECT inn FROM target_verdicts WHERE verdict LIKE '%не покуп%'"
        ).fetchall():
            не_покупатели.add(str(и))
except Exception as e:                                         # noqa: BLE001
    print("вердикты гейта не прочитались:", str(e)[:70])
print("осуждённых гейтом «не покупатель»: %d" % len(не_покупатели))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print("\nстрок в группе «%s»: %d" % (ГРУППА, len(в_группе)))

счёт = Counter()
видели, годные, корп = set(), [], 0
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["1 нет карточки получателя"] += 1
        continue
    инн = "".join(ч for ч in str(getattr(rec, "inn", "") or "") if ч.isdigit())
    почта = str(getattr(rec, "email", "") or "").strip().lower()
    if not инн or not почта:
        счёт["2 нет ИНН или почты"] += 1
        continue
    if почта in мёртвые:
        счёт["3 приговор пробы: адрес мёртв"] += 1
        continue
    if инн in видели:
        счёт["4 дубль строки той же фирмы"] += 1
        continue
    видели.add(инн)
    if инн in сделано_инн:
        счёт["5 письмо уже есть"] += 1
        continue
    if попыток[инн] >= 3:
        счёт["6 исчерпал три попытки"] += 1
        continue
    причина = cs._guard(inn=инн, email=почта)
    if причина:
        счёт["7 заслон: %s" % причина.split(":")[0]] += 1
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    свой = mx in СВОЙ_СЕРВЕР
    if свой:
        корп += 1
    if минус_класс(getattr(rec, "okved", ""), getattr(rec, "company_name", "")):
        счёт["9 минус-класс по ОКВЭД"] += 1
        continue
    if инн in не_покупатели:
        счёт["10 гейт: не покупатель"] += 1
        continue
    годные.append((rid, инн, почта, свой))

print("\n=== ЧТО ОТСЕЯЛОСЬ ===")
for к in sorted(счёт):
    print("  %-42s %d" % (к, счёт[к]))

без_корп = [г for г in годные if not г[3]]
print("\n=== СКОЛЬКИМ МОЖНО НАПИСАТЬ ===")
print("  всего пригодных компаний:            %d" % len(годные))
print("  из них на чужих почтовиках (mail/ya) %d  <- идут в автоотправку"
      % len(без_корп))
print("  из них на своих серверах компании    %d  <- только вручную"
      % (len(годные) - len(без_корп)))
