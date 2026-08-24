# -*- coding: utf-8 -*-
"""Сколько кандидатов можно поставить в генерацию прямо сейчас.

Тот же отбор, что и в partiya_gen (резюм по журналу, приговоры проб,
дубли по ИНН, три попытки, заслон подтверждения, направление, корпоративность),
но БЕЗ гейта адресата: гейт платный, он спрашивает провайдера про каждого
кандидата. Его отсев показываем отдельно — по факту сегодняшних прогонов.

Считаем сразу три раскладки: всего, по направлениям и по типу почтовика.
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.ai_letter import target_division                  # noqa: E402
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.confirm import ConfirmSend                        # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.suppression import Suppression                    # noqa: E402

ГРУППА = "Партия 935"
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
        except Exception:  # noqa: BLE001
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

_снятые = set()
with store._lock:
    for (_инн,) in store._conn.execute(
            "SELECT DISTINCT r.inn FROM confirm_reviews c "
            "LEFT JOIN recipients r ON r.id=c.recipient_id "
            "WHERE c.status='skipped' AND (c.reason LIKE '%не наш%' "
            "  OR c.reason LIKE '%вне профиля%' "
            "  OR c.reason LIKE '%не покупатель%')").fetchall():
        _ц = "".join(c for c in str(_инн or "") if c.isdigit())
        if _ц:
            _снятые.add(_ц)
сделано_инн -= _снятые

_мёртвые = set()
from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА                # noqa: E402
with store._lock:
    for (_а,) in store._conn.execute(
            "SELECT email FROM addr_probe WHERE verdict IN (?, ?)",
            (НЕТ_ЯЩИКА, НЕТ_MX)).fetchall():
        if _а:
            _мёртвые.add(str(_а).strip().lower())

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print("строк в группе «%s»: %d" % (ГРУППА, len(в_группе)))
print("приговоров «мёртв»: %d | компаний с готовым письмом: %d | "
      "возвращено после снятия по профилю: %d"
      % (len(_мёртвые), len(сделано_инн), len(_снятые)))

счёт = Counter()
годные = []
видели = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["строки группы без карточки получателя"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if email in _мёртвые:
        счёт["приговор пробы: адрес мёртв"] += 1
        continue
    if inn in видели:
        счёт["дубль строки той же фирмы"] += 1
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
        счёт["заслон: %s" % причина.split(":")[0]] += 1
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    свой = mx in СВОЙ_СЕРВЕР
    try:
        _req = q._request(rec)
    except Exception:  # noqa: BLE001
        счёт["запрос не собрался"] += 1
        continue
    _d = str(_req.get("target_division") or "")
    if _d not in ("kc", "meyer"):
        _d, _ = target_division(_req, default="kc")
    годные.append((_d, свой))
    счёт["ГОДЕН"] += 1

print("\n=== ПОЧЕМУ ОТСЕЯЛИСЬ ===")
for к, н in счёт.most_common():
    if к != "ГОДЕН":
        print("  %-46s %6d" % (к, н))

раскладка = Counter(годные)
print("\n=== ГОДНЫ К ГЕНЕРАЦИИ: %d ===" % счёт["ГОДЕН"])
for напр in ("kc", "meyer"):
    публ = раскладка.get((напр, False), 0)
    корп = раскладка.get((напр, True), 0)
    print("  %-8s всего %5d   публичный почтовик %5d   свой сервер %5d"
          % (напр.upper(), публ + корп, публ, корп))
всего_публ = sum(н for (_d, с), н in раскладка.items() if not с)
всего_корп = sum(н for (_d, с), н in раскладка.items() if с)
print("  %-8s всего %5d   публичный почтовик %5d   свой сервер %5d"
      % ("ИТОГО", счёт["ГОДЕН"], всего_публ, всего_корп))

print("\n=== ПОПРАВКА НА ГЕЙТ АДРЕСАТА (он платный, здесь не звался) ===")
print("  по сегодняшним прогонам гейт снимал часть кандидатов;")
print("  ниже — доля брака и отсева, чтобы прикинуть выход готовых писем:")
print("  прогон 500 → 368 писем (74%), прогон 300 → 215 писем (72%)")
print("  то есть из %d кандидатов ожидаемо выйдет ~%d готовых писем"
      % (счёт["ГОДЕН"], int(счёт["ГОДЕН"] * 0.73)))
