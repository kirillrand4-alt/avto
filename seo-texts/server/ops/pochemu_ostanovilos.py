# -*- coding: utf-8 -*-
"""Почему отправка встала и уйдут ли письма через другой пул.

Пул выбирается по ПОЧТОВОМУ ПРОВАЙДЕРУ ПОЛУЧАТЕЛЯ (provider_split.routing,
match_recipient_provider=true): письмо на ящик Mail.ru отправляется только с
наших ящиков mail.ru, на Яндекс — только с яндексовых. Так делают, чтобы
репутация набиралась внутри одной пары «наш домен — их провайдер».
Перекладывания в чужой пул НЕТ: если в своём пуле нет пригодного ящика,
pick_mailbox возвращает None, письмо возвращается в очередь и ждёт.

Здесь: сколько готовых писем ждёт какой пул и сколько в этом пуле осталось
ёмкости на сегодня.

    python zapusk_svoego_skripta.py ops/pochemu_ostanovilos.py
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd, g = deps.sender, deps.gates
сейчас = datetime.now(timezone.utc)

маршрут = cfg.get("provider_split.routing", {}) or {}
print("маршрутизация пулов (провайдер получателя -> наш пул):")
for k, v in маршрут.items():
    print(f"  {k:<10} -> {v}")
print(f"  match_recipient_provider: "
      f"{cfg.get('provider_split.match_recipient_provider', True)}\n")

# --- сколько готовых писем ждёт какой пул --- #
with store._lock:
    ряд = store._conn.execute(
        "SELECT COALESCE(r.mx_provider,'unknown'), COUNT(*) "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='approved' GROUP BY 1").fetchall()
ждут = Counter()
print("готовые письма по пулам:")
for пров, n in ряд:
    пул = маршрут.get(str(пров).lower()) or маршрут.get("other") or "(нет пула)"
    ждут[пул] += n
    print(f"  провайдер {str(пров):<10} {n:>4} писем -> {пул}")
print()

# --- ёмкость каждого пула на сегодня --- #
пулы = cfg.provider_pools()
for пул, ящики in пулы.items():
    свободно = 0
    строки = []
    for mid in ящики:
        r = snd.mailbox_readiness(mid)
        готов = snd.can_send_now(mid, now=сейчас)
        остаток = max(0, int(r.daily_limit) - int(r.sent_today)) if готов else 0
        свободно += остаток
        причины = list(r.reasons) or ["-"]
        строки.append(f"    {mid:<40} лимит {r.daily_limit:>3} "
                      f"сегодня {r.sent_today:>3} осталось {остаток:>3}  "
                      f"{'МОЖЕТ' if готов else 'НЕ МОЖЕТ'} {причины}")
    print(f"пул {пул}: ждёт писем {ждут.get(пул, 0)}, "
          f"свободной ёмкости сегодня {свободно}")
    for s in строки:
        print(s)
    print()

print("Итог: письма ждут СВОЙ пул. Пока в нём нет пригодного ящика, они "
      "лежат в очереди — в чужой пул они не переедут.")
