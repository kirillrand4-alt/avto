# -*- coding: utf-8 -*-
"""Что осталось в очереди на завтра и что с этим надо сделать.

Сегодняшняя отправка собиралась так: сгенерировали -> механический QA ->
рецензент сверил каждое утверждение письма с САЙТОМ компании -> «годно»
перевели в автоотправку, «не годно» оставили в pending. Чтобы завтрашняя
очередь была такой же, надо прогнать рецензентом ровно то, что ещё не
смотрено, и перевести годное.

Здесь считаем: сколько pending всего, сколько уже отрецензировано и с каким
вердиктом, сколько не смотрено ни разу, и сколько из них отсеется заранее
(корпоративный сервер, мёртвый адрес, чужое направление).

    python zapusk_svoego_skripta.py ops/chto_ostalos_na_zavtra.py
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# вердикты рецензента по id письма
рец = {}
ж = r"C:\sender\_ops\rezenzii-pisem.jsonl"
for s in io.open(ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("id") is not None:
        рец[int(z["id"])] = str(z.get("verdict") or "?")

with store._lock:
    ряд = store._conn.execute(
        """SELECT c.id, c.campaign_id, c.email, c.panel_json,
                  COALESCE(p.verdict,'(нет пробы)') AS проба,
                  COALESCE(r.mx_provider,'unknown') AS провайдер
             FROM confirm_reviews c
             LEFT JOIN addr_probe p ON p.email=lower(c.email)
             LEFT JOIN recipients r ON r.id=c.recipient_id
            WHERE c.status='pending' AND COALESCE(c.kind,'outbound')<>'reply'
        """).fetchall()

print(f"писем в pending: {len(ряд)}\n")

по_кампаниям = Counter()
по_рецензии = Counter()
на_рецензию = []
отсев = Counter()
СВОЙ_СЕРВЕР = ("other", "unknown", "")
for cid, кампания, email, pj, проба, провайдер in ряд:
    по_кампаниям[кампания] += 1
    в = рец.get(int(cid))
    по_рецензии[в or "не смотрено"] += 1
    if проба in ("нет ящика", "нет MX"):
        отсев["мёртвый адрес (проба)"] += 1
        continue
    if str(провайдер).lower() in СВОЙ_СЕРВЕР:
        отсев["корпоративный почтовый сервер"] += 1
        continue
    try:
        d = str((json.loads(pj or "{}") or {}).get("letter_division") or "")
    except Exception:                                            # noqa: BLE001
        d = ""
    if в is None:
        на_рецензию.append((cid, d))

print("по кампаниям:", dict(по_кампаниям.most_common()))
print("по рецензии:", dict(по_рецензии.most_common()))
print("\nотсеются до рецензии:")
for к, n in отсев.most_common():
    print(f"  {n:>5}  {к}")
print(f"\nнадо отрецензировать: {len(на_рецензию)}")
print("  по направлению письма:",
      dict(Counter(d or "(пусто)" for _i, d in на_рецензию).most_common()))
print(f"\nуже «годно», но ещё в pending (можно переводить сразу): "
      f"{sum(1 for cid, *_ in ряд if рец.get(int(cid)) == 'годно')}")
