# -*- coding: utf-8 -*-
"""Пройдут ли вебинарные письма заслоны при РУЧНОЙ отправке.

Спрашиваем ровно то, что спросит confirm.approve перед отправкой:
_zhdyot_verdikta (ждём вердикт пробы по адресу, введённому руками),
_chuzhoy_inn, _guard (стоп-лист, мёртвый адрес, контакт моложе 90 дней)
и _division_blocked. Ничего не отправляем - только считаем вердикты.

Заслон подтверждения НЕ читает пометку «повтор разрешён»: она живёт в
заслоне ЭТАПА ОТПРАВКИ (auto_send), а здесь другой рубеж. Поэтому важно
знать заранее, скольким письмам понадобится второе подтверждение.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.confirm import ConfirmSend                              # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.suppression import Suppression                          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

with store._lock:
    ids = [р[0] for р in store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE dedup_key LIKE 'vebinar28:%' "
        "AND status='pending' ORDER BY id").fetchall()]

счёт = Counter()
примеры = {}
for кид in ids:
    строка = cs.get(кид)
    если = None
    for имя, зов in (
            ("ждёт вердикта пробы", lambda: cs._zhdyot_verdikta(строка)),
            ("чужой ИНН", lambda: cs._chuzhoy_inn(строка)),
            ("заслон подтверждения", lambda: cs._guard(
                inn=строка.get("inn"), email=строка["email"])),
            ("гейт направлений", lambda: cs._division_blocked(строка))):
        try:
            ответ = зов()
        except Exception as ex:                                   # noqa: BLE001
            ответ = f"{type(ex).__name__}: {str(ex)[:60]}"
        if ответ:
            если = f"{имя}: {ответ}"
            break
    ключ = "ПРОЙДЁТ" if если is None else если.split(":")[1].split("<")[0].strip()
    if если is None:
        ключ = "ПРОЙДЁТ"
    счёт[ключ] += 1
    примеры.setdefault(ключ, []).append((кид, строка.get("email"), если))

print(f"вебинарных карточек в очереди: {len(ids)}\n")
for ключ, н in счёт.most_common():
    print(f"{н:>4}  {ключ}")
    for кид, поч, почему in примеры[ключ][:3]:
        print(f"        №{кид} {поч}: {почему or '—'}")
