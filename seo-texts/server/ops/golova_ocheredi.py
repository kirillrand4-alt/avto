# -*- coding: utf-8 -*-
"""Первые письма очереди: не заперта ли голова непроходимыми письмами.

Цикл берёт партию ORDER BY scheduled_at, id LIMIT batch(10). Если первые
десять писем адресованы в пул, где сейчас нет ни одного пригодного ящика,
цикл каждую минуту берёт ИХ ЖЕ, возвращает в очередь и на этом заканчивает
проход — письма, стоящие следом и вполне отправимые, он не видит никогда.

    python zapusk_svoego_skripta.py ops/golova_ocheredi.py
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (recipient_tz_name, window_from,      # noqa: E402
                              within_window_now)
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.wiring import build_deps                               # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd = deps.live_sender or deps.sender
сейчас = datetime.now(timezone.utc)
win = window_from(store, cfg)
маршрут = cfg.get("provider_split.routing", {}) or {}

with store._lock:
    ряд = store._conn.execute(
        """SELECT m.id, m.recipient_id, m.campaign_id, m.scheduled_at
             FROM messages m
            WHERE m.status='scheduled' AND m.scheduled_at <= ?
              AND (SELECT cr.status FROM confirm_reviews cr
                    WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1)
                  IN ('approved','edited')
            ORDER BY m.scheduled_at, m.id LIMIT 30""",
        (сейчас.isoformat(),)).fetchall()

print(f"порядок, в котором цикл берёт письма (партия = 10):\n")
print(f"{'№':>3} {'письмо':>7} {'слот':<17} {'пул':<14} {'почта':<32} ящик")
уйдёт_в_первой = 0
for i, (mid, rid, cid, ts) in enumerate(ряд, 1):
    r = store.get_recipient(int(rid))
    камп = store.get_campaign(int(cid))
    пров = str(getattr(r, "mx_provider", "") or "unknown").lower()
    пул = маршрут.get(пров) or маршрут.get("other") or "?"

    class _M:
        id = mid
    в_окне = within_window_now(win, recipient_tz_name(win, r), сейчас)
    я = snd.pick_mailbox(r, камп, now=сейчас, message=_M()) if в_окне else None
    if i <= 10 and я:
        уйдёт_в_первой += 1
    метка = я or ("вне окна" if not в_окне else "НЕТ ЯЩИКА")
    рубеж = " <-- граница партии" if i == 10 else ""
    print(f"{i:>3} {mid:>7} {str(ts)[11:16]:<17} {пул:<14} "
          f"{str(getattr(r, 'email', ''))[:30]:<32} {метка}{рубеж}")

print(f"\nиз первых десяти уйдёт: {уйдёт_в_первой}")
if уйдёт_в_первой == 0:
    print("ГОЛОВА ОЧЕРЕДИ ЗАПЕРТА: цикл будет брать эти же письма каждую "
          "минуту и не дойдёт до отправимых, стоящих ниже.")
