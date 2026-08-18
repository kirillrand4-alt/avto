
# -*- coding: utf-8 -*-
"""Кому в партии 935 реально можно написать прямо сейчас.

Владелец залил в группу новые компании и спрашивает, есть ли среди них
подходящие. Считаем ТЕМ ЖЕ отбором, каким пойдёт генерация, чтобы ответ не
разошёлся с делом:

  * письмо уже есть (по ИНН в журнале партии) - пропуск;
  * заслон подтверждения (стоп-лист, мёртвый адрес, контакт моложе 90 дней);
  * минус-класс - медицина (решение владельца 18.08), теперь режется до
    модели;
  * почтовик получателя: публичный или свой сервер - считаем отдельно, на
    свои шлём только руками;
  * направление считаем той же цепочкой, что и генерация.

Модель не зовём вовсе: гейт адресата по роду деятельности здесь не
спрашиваем, он стоит уже в самой генерации.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import target_division                      # noqa: E402
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.confirm import ConfirmSend                            # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.suppression import Suppression                        # noqa: E402
from sender.target_gate import минус_класс                        # noqa: E402

RE_ПРОБЕЛЫ = re.compile(r"\s+")
ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
СВОЙ_СЕРВЕР = ("other", "unknown", "")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))

сделано_инн = set()
for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                             # noqa: BLE001
        continue
    if z.get("ок") or z.get("тело"):
        сделано_инн.add(str(z.get("inn") or ""))

группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print(f"строк в группе «{ГРУППА}»: {len(в_группе)}")
print(f"ИНН с готовым письмом по журналу: {len(сделано_инн)}")

счёт = Counter()
годные = {"публичный": [], "свой сервер": []}
видели = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["строки нет"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    имя = str(getattr(rec, "company_name", "") or "")
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    if inn in видели:
        счёт["дубль строки той же фирмы"] += 1
        continue
    видели.add(inn)
    if inn in сделано_инн:
        счёт["письмо уже есть"] += 1
        continue
    if минус_класс(getattr(rec, "okved", ""), имя):
        счёт["минус-класс: медицина"] += 1
        continue
    причина = cs._guard(inn=inn, email=email)
    if причина:
        счёт[f"заслон: {причина.split(':')[0]}"] += 1
        continue
    try:
        req = q._request(rec)
        _я = str(req.get("target_division") or "")
        div = _я if _я in ("kc", "meyer") else target_division(req,
                                                              default="kc")[0]
    except Exception:                                             # noqa: BLE001
        счёт["запрос не собрался"] += 1
        continue
    mx = str(getattr(rec, "mx_provider", "") or "").strip().lower()
    куда = "свой сервер" if mx in СВОЙ_СЕРВЕР else "публичный"
    счёт[f"ГОДЕН: {div} / {куда}"] += 1
    годные[куда].append((rid, имя, div, str(getattr(rec, "okved", ""))))

print("\nразбор:")
for k, n in счёт.most_common():
    print(f"  {n:>5}  {k}")
итого = sum(len(v) for v in годные.values())
print(f"\nвсего к генерации: {итого}")
for куда, сп in годные.items():
    print(f"\n{куда}: {len(сп)}, первые 12:")
    for rid, имя, div, ок in сп[:12]:
        имя_ = re.sub(RE_ПРОБЕЛЫ, " ", имя)[:44]
        print(f"  #{rid:<7} {div:<6} {имя_:<46} ОКВЭД {ок}")
