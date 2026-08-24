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

from sender.validation import _BASE_ROLE_PREFIXES as _РОЛИ  # noqa: E402

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
    # ПАСПОРТ САЙТА и РОЛЕВОЙ АДРЕС — владелец 24.08 спросил про оба.
    # Паспорт письму не обязателен (генерация работает и без него), но
    # без него письмо строится на вывеске из базы, а не на деле компании.
    паспорт = {}
    try:
        паспорт = q._site_facts(inn) or {}
    except Exception:  # noqa: BLE001
        паспорт = {}
    полей = sum(1 for к in ("цитата", "продукция", "оборудование_линии",
                            "сырьё", "масштаб", "мощности")
                if паспорт.get(к))
    роль = email.split("@")[0].strip().lower() in _РОЛИ
    годные.append((_d, свой, полей, роль))
    счёт["ГОДЕН"] += 1

print("\n=== ПОЧЕМУ ОТСЕЯЛИСЬ ===")
for к, н in счёт.most_common():
    if к != "ГОДЕН":
        print("  %-46s %6d" % (к, н))

print("\n=== ГОДНЫ К ГЕНЕРАЦИИ: %d ===" % счёт["ГОДЕН"])
for напр in ("kc", "meyer"):
    свои = [г for г in годные if г[0] == напр]
    публ = sum(1 for г in свои if not г[1])
    print("  %-8s всего %5d   публичный почтовик %5d   свой сервер %5d"
          % (напр.upper(), len(свои), публ, len(свои) - публ))
всего_публ = sum(1 for г in годные if not г[1])
print("  %-8s всего %5d   публичный почтовик %5d   свой сервер %5d"
      % ("ИТОГО", счёт["ГОДЕН"], всего_публ, счёт["ГОДЕН"] - всего_публ))

print("\n=== ПАСПОРТ САЙТА (сколько полей заполнено из шести) ===")
по_полям = Counter(г[2] for г in годные)
for полей in sorted(по_полям, reverse=True):
    н = по_полям[полей]
    метка = "  ← паспорта НЕТ вовсе" if полей == 0 else ""
    print("  полей %d: %5d  (%4.1f%%)%s"
          % (полей, н, 100.0 * н / max(1, счёт["ГОДЕН"]), метка))
с_паспортом = sum(1 for г in годные if г[2] > 0)
print("  с паспортом: %d (%.1f%%), без паспорта: %d (%.1f%%)"
      % (с_паспортом, 100.0 * с_паспортом / max(1, счёт["ГОДЕН"]),
         счёт["ГОДЕН"] - с_паспортом,
         100.0 * (счёт["ГОДЕН"] - с_паспортом) / max(1, счёт["ГОДЕН"])))

print("\n=== РОЛЕВЫЕ АДРЕСА (info@, sales@, office@ и т.п.) ===")
ролевых = sum(1 for г in годные if г[3])
print("  ролевых:   %5d (%.1f%%)" % (ролевых, 100.0 * ролевых / max(1, счёт["ГОДЕН"])))
print("  именных:   %5d (%.1f%%)"
      % (счёт["ГОДЕН"] - ролевых,
         100.0 * (счёт["ГОДЕН"] - ролевых) / max(1, счёт["ГОДЕН"])))

print("\n=== ПЕРЕСЕЧЕНИЕ: ПАСПОРТ х РОЛЬ ===")
print("  %-34s %6s" % ("", "штук"))
for имя, усл in (("паспорт есть + именной адрес", lambda г: г[2] > 0 and not г[3]),
                 ("паспорт есть + ролевой адрес", lambda г: г[2] > 0 and г[3]),
                 ("паспорта нет + именной адрес", lambda г: г[2] == 0 and not г[3]),
                 ("паспорта нет + ролевой адрес", lambda г: г[2] == 0 and г[3])):
    print("  %-34s %6d" % (имя, sum(1 for г in годные if усл(г))))

print("\n=== ПОПРАВКА НА ГЕЙТ АДРЕСАТА (он платный, здесь не звался) ===")
print("  по сегодняшним прогонам гейт снимал часть кандидатов;")
print("  ниже — доля брака и отсева, чтобы прикинуть выход готовых писем:")
print("  прогон 500 → 368 писем (74%), прогон 300 → 215 писем (72%)")
print("  то есть из %d кандидатов ожидаемо выйдет ~%d готовых писем"
      % (счёт["ГОДЕН"], int(счёт["ГОДЕН"] * 0.73)))
