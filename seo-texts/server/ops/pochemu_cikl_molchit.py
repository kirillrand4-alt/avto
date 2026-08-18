# -*- coding: utf-8 -*-
"""Пройти путь цикла автоотправки по каждому письму, ничего не отправляя.

Цикл: claim_approved_due -> окно получателя -> подбор ящика -> отправка.
Здесь повторяем первые три шага и печатаем, на каком письмо останавливается.
Отправки нет: sender не трогаем.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,       # noqa: E402
                              window_from, within_window_now)
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = build_deps(cfg, store, dry_run=True).sender
сейчас = datetime.now(timezone.utc)
win = window_from(store, cfg)
print(f"окно, каким его видит цикл: {win}")
print(f"сейчас {сейчас.strftime('%H:%M')} UTC\n")

with store._lock:
    ряд = store._conn.execute(
        "SELECT m.id, m.recipient_id, m.campaign_id, m.scheduled_at "
        "FROM messages m JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE m.status='scheduled' AND c.status IN ('approved','edited') "
        "AND m.scheduled_at<=? ORDER BY m.scheduled_at LIMIT 200",
        (сейчас.isoformat(),)).fetchall()
print(f"писем, которые возьмёт claim_approved_due: {len(ряд)}\n")

свод = Counter()
пример = {}
for mid, rid, cid, ts in ряд:
    r = store.get_recipient(int(rid))
    if r is None:
        свод["нет получателя"] += 1
        continue
    tz = recipient_tz_name(win, r)
    if not within_window_now(win, tz, сейчас):
        к = f"вне окна получателя ({tz})"
        свод[к] += 1
        пример.setdefault(к, (mid, r.email, next_slot(win, tz, сейчас)))
        continue
    камп = store.get_campaign(int(cid))

    class _M:
        id = mid
    ящик = snd.pick_mailbox(r, камп, now=сейчас, message=_M())
    if ящик:
        свод[f"ГОТОВО к отправке -> {ящик}"] += 1
        пример.setdefault(f"ГОТОВО к отправке -> {ящик}", (mid, r.email, ""))
    else:
        свод["нет пригодного ящика"] += 1
        пример.setdefault("нет пригодного ящика", (mid, r.email, ""))

for к, n in свод.most_common():
    п = пример.get(к)
    print(f"  {n:>4}  {к}" + (f"   напр. #{п[0]} {п[1]} {п[2]}" if п else ""))
