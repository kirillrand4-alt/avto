# -*- coding: utf-8 -*-
"""Поднять ручной потолок ящиков до рамп-кривой (35 -> 50).

Замер 18.08: очередь встала не из-за прогрева, а из-за РУЧНОГО потолка.
В panel_settings['send_limits'] на каждый из 14 боевых ящиков стоит 35, а
рамп-кривая на их днях прогрева (7-13) разрешает 50. Потолок работает
только вниз, поэтому 15 писем на ящик просто не выпускались.

Это не разгон прогрева: 50 - это ровно то, что кривая уже разрешила
(yandex/mailru: [3,5,8,12,18,25,32,40,50], плато с 8-го дня). Ящик, чей
день прогрева ещё не дорос, всё равно получит своё значение кривой -
min(кривая, потолок).

Без --применить только показывает.

    python zapusk_svoego_skripta.py ops/podnyat_potolok_do_rampy.py
    python zapusk_svoego_skripta.py ops/podnyat_potolok_do_rampy.py --применить 50
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.ramp import curve_value                              # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

ПРИМЕНИТЬ = "--применить" in sys.argv
НОВЫЙ = 50
for a in sys.argv[1:]:
    if a.isdigit():
        НОВЫЙ = int(a)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = build_deps(cfg, store, dry_run=True).sender

было = store.get_setting("send_limits")
if isinstance(было, str) and было:
    было = json.loads(было)
было = было if isinstance(было, dict) else {}
пер = dict(было.get("per_mailbox") or {})

print(f"новый потолок: {НОВЫЙ}\n")
print(f"{'ящик':<40} {'потолок':>8} {'кривая':>7} {'станет':>7} "
      f"{'сегодня':>8} {'добавит':>8}")
добавка = 0
for mb in cfg.mailboxes():
    if mb.mailbox_id not in пер:
        continue
    r = snd.mailbox_readiness(mb.mailbox_id)
    к = curve_value(cfg.ramp_curve(mb.provider), r.ramp_day)
    станет = min(к, НОВЫЙ)
    рост = max(0, станет - int(r.daily_limit))
    добавка += рост
    пер[mb.mailbox_id] = НОВЫЙ
    print(f"  {mb.mailbox_id:<38} {int(r.daily_limit):>8} {к:>7} "
          f"{станет:>7} {r.sent_today:>8} {рост:>8}")
print(f"\nдополнительных слотов на сегодня: {добавка}")
print("(у ящиков, закрытых гейтом репутации, слоты не появятся — "
      "гейт считается отдельно от лимита)")

if not ПРИМЕНИТЬ:
    print("\nсухой прогон: настройка не тронута. Применить — --применить")
    raise SystemExit(0)

новое = dict(было)
новое["per_mailbox"] = пер
store.set_setting("send_limits", новое)
проверка = store.get_setting("send_limits")
if isinstance(проверка, str):
    проверка = json.loads(проверка)
знач = set((проверка or {}).get("per_mailbox", {}).values())
print(f"\nзаписано. потолки теперь: {sorted(знач)}")
for mb in cfg.mailboxes():
    if mb.mailbox_id in пер:
        r = snd.mailbox_readiness(mb.mailbox_id)
        print(f"  {mb.mailbox_id:<38} лимит {r.daily_limit} "
              f"сегодня {r.sent_today} готов={r.ready} {list(r.reasons)}")
