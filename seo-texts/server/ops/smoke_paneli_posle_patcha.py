# -*- coding: utf-8 -*-
"""Смоук после выкатки: панель собирается, цифры считаются, гейт живой.

Проверяем ровно то, что увидит владелец: дашборд с новой строкой, гейты и
разбивка по ящикам. Если панель не соберётся - лучше узнать здесь, а не по
белому экрану после рестарта службы.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
д = deps.analytics.dashboard()
g = д["global"]
print("ГЛОБАЛЬНО:")
print(f"  отправлено {g['total_sent']}, отбивок {g['total_bounced']} "
      f"({g['global_bounce_rate']}%), жалоб {g['total_complaints']}")
print(f"  ОТКЛОНЕНО ПОЧТОВИКОМ: {g.get('total_rejected')} "
      f"({g.get('global_reject_rate')}%)")

строки = [м for м in д["mailboxes"] if (м.get("rejected") or 0) > 0]
print(f"\nящиков с отказами: {len(строки)}")
for м in строки:
    print(f"  {м['mailbox_id']:<40} отказов {м['rejected']:>3} "
          f"({м['reject_rate']}%), ушло сегодня {м['sent_today']:>3}, "
          f"пауза={м['paused']}")

trips = deps.gates.active_trips()
print(f"\nсработавшие гейты: {len(trips)}")
for t in trips[:10]:
    print(f"  {t.scope}/{t.target}: {t.metric} {t.value} при пороге {t.threshold}")

порог = cfg.gates()
print(f"\nпорог отказов на ящик: {getattr(порог, 'mailbox_reject_pct', '?')}%")
from sender.otkaz_spam import porogi                               # noqa: E402
print(f"остановка: ящик {porogi(cfg)[0]} отказа, направление {porogi(cfg)[1]}")
