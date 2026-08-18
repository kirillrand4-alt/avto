# -*- coding: utf-8 -*-
"""Откуда берётся дневной лимит ящика и что мешает отправить всё сегодня.

Лимит = рамп-кривая провайдера на рамп-дне, ПРИЖАТАЯ ручным потолком из
панели (send_limits). Ручной потолок работает только вниз. Печатаем оба
источника и остаток очереди, чтобы считать, что и на сколько поднимать.

    python zapusk_svoego_skripta.py ops/limity_otkuda.py
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.ramp import curve_value                              # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd = deps.sender
сейчас = datetime.now(timezone.utc)

print("рамп-кривые из sender.yaml (индекс = день прогрева):")
for пров in ("yandex", "mailru", "google", "outlook"):
    try:
        print(f"  {пров:<8} {cfg.ramp_curve(пров)}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  {пров:<8} нет кривой ({str(ex)[:50]})")

ручной = store.get_setting("send_limits")
print(f"\nручной потолок панели send_limits: {ручной!r}")

print(f"\n{'ящик':<40} {'пров':<8} {'рамп':>5} {'кривая':>7} {'лимит':>6} "
      f"{'сегодня':>8}")
for mb in cfg.mailboxes():
    r = snd.mailbox_readiness(mb.mailbox_id)
    try:
        к = curve_value(cfg.ramp_curve(mb.provider), r.ramp_day)
    except Exception:                                            # noqa: BLE001
        к = 0
    print(f"  {mb.mailbox_id:<38} {mb.provider:<8} {r.ramp_day:>5} "
          f"{к:>7} {r.daily_limit:>6} {r.sent_today:>8}")

with store._lock:
    ряд = store._conn.execute(
        "SELECT COALESCE(r.mx_provider,'unknown'), COUNT(*) "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='approved' GROUP BY 1").fetchall()
маршрут = cfg.get("provider_split.routing", {}) or {}
ждут = Counter()
for пров, n in ряд:
    ждут[маршрут.get(str(пров).lower()) or маршрут.get("other") or "?"] += n
print("\nосталось готовых писем по пулам:")
for пул, n in ждут.most_common():
    print(f"  {пул:<16} {n}")
