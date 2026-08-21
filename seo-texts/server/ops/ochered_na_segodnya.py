# -*- coding: utf-8 -*-
"""Что стояло на сегодня и не ушло: разбор перед ручным дотолкиванием.

«Стояло на сегодня» - письма со статусом scheduled, чей слот приходится на
21.08. Показываем по каждому: направление письма, какой ящик подберётся,
что скажут заслоны и хватит ли ящиков по дневному лимиту.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.ramp import daily_send_limit                            # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs, живой = deps.confirm, getattr(deps.confirm, "_sender", None)

with store._lock:
    ряды = store._conn.execute(
        "SELECT m.id mid, m.status mst, m.campaign_id, "
        "       substr(m.scheduled_at,1,16) слот, cr.id rid, cr.status cst, "
        "       COALESCE(cr.email, r.email) email, r.company_name "
        "  FROM messages m "
        "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
        "  LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN ('scheduled','queued') ORDER BY m.scheduled_at"
    ).fetchall()
print(f"писем в статусе scheduled/queued: {len(ряды)}")
по_дням = Counter(str(р[3])[:10] for р in ряды)
print("по дате слота:", dict(sorted(по_дням.items())))

сегодня = [р for р in ряды if str(р[3])[:10] <= "2026-08-21"]
print(f"\nстояло на сегодня и раньше: {len(сегодня)}")
камп = Counter(f"камп{р[2]} карточка={р[5]}" for р in сегодня)
for к, н in камп.most_common():
    print(f"  {н:>4}  {к}")

# запас ящиков
print("\nзапас по ящикам (лимит рампы минус ушедшее сегодня):")
запас = Counter()
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(ст, "ramp_day", 0) if ст else 0
    ушло = getattr(ст, "sent_today", 0) if ст else 0
    лим = живой._daily_limit(mb.provider, рд, mb.mailbox_id) if живой else \
        daily_send_limit(cfg, mb.provider, рд)
    своб = max(0, лим - ушло)
    запас[str(mb.division)] += своб
    if своб:
        print(f"  {mb.mailbox_id:<42} {mb.division:<6} {ушло}/{лим} "
              f"свободно {своб}")
print(f"итого свободно: {dict(запас)}")
