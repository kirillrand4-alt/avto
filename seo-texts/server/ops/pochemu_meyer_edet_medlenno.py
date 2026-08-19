# -*- coding: utf-8 -*-
"""Почему мейеровские письма уходят по три штуки: проиграть решение цикла.

Не гадаем «окно/пейсинг/лимит», а прогоняем для КАЖДОГО ждущего письма ту же
цепочку, что автоотправка: созрело ли (scheduled_at), открыт ли час получателя,
и что вернёт подбор ящика — с разбором, кто именно из ящиков отпал и почему.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (window_from, within_window_now,          # noqa: E402
                              recipient_tz_name, next_slot)
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

КАМПАНИЯ = 11
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
now = datetime.now(timezone.utc)
win = window_from(store, cfg)

print("== сейчас ==")
print("  UTC:", now.strftime("%Y-%m-%d %H:%M"),
      "| МСК:", now.astimezone(__import__("zoneinfo").ZoneInfo(
          "Europe/Moscow")).strftime("%H:%M"))
print("  окно:", win)
print("  пейсинг min_interval_sec:", cfg.get("send_pacing.min_interval_sec", 90))
print("  автоотправка включена:", store.get_setting("auto_send_enabled", False))

print("\n== что ушло сегодня (кампания 11) ==")
with store._lock:
    ушли = store._conn.execute(
        "SELECT m.id, m.mailbox_id, m.sent_at, r.email, r.tz "
        "FROM messages m JOIN confirm_reviews c ON c.message_id=m.id "
        "LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE c.campaign_id=? AND m.status='sent' "
        "AND date(m.sent_at)=date('now') ORDER BY m.sent_at",
        (КАМПАНИЯ,)).fetchall()
for r in ушли:
    print(f"  #{r['id']:<6} {str(r['sent_at'])[:16]}  {r['mailbox_id']:<38} "
          f"-> {r['email']}  tz={r['tz']}")
print("  всего:", len(ушли))

print("\n== ждущие письма кампании 11 ==")
with store._lock:
    ждут = store._conn.execute(
        "SELECT m.id, m.recipient_id, m.campaign_id, m.status, m.scheduled_at "
        "FROM messages m JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE c.campaign_id=? AND m.status IN ('scheduled','sending') "
        "AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id "
        "     ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited') "
        "ORDER BY m.scheduled_at, m.id", (КАМПАНИЯ,)).fetchall()
print("  одобрено и ждёт:", len(ждут))

нез = Counter()
for r in ждут:
    нез[str(r["status"])] += 1
print("  по статусу:", dict(нез))

созрели = [r for r in ждут if str(r["scheduled_at"] or "") <= now.strftime(
    "%Y-%m-%dT%H:%M:%S")]
print(f"  созрели (scheduled_at <= сейчас): {len(созрели)} из {len(ждут)}")
поздние = sorted({str(r["scheduled_at"])[:16] for r in ждут
                  if r not in созрели})[:8]
if поздние:
    print("  ближайшие несозревшие:", поздние)

# ---- проигрываем подбор ящика ------------------------------------------- #
from sender.sender import Sender                                       # noqa: E402
try:
    snd = Sender(config=cfg, store=store, dry_run=True)
except TypeError:
    snd = Sender(cfg, store)

причины = Counter()
примеры = {}
пулы = cfg.provider_pools()
for r in ждут[:400]:
    rec = store.get_recipient(r["recipient_id"])
    camp = store.get_campaign(r["campaign_id"])
    msg_rows = None
    with store._lock:
        msg_rows = store._conn.execute(
            "SELECT * FROM messages WHERE id=?", (r["id"],)).fetchone()
    from sender.store import _row_to_message                           # noqa: E402
    m = _row_to_message(msg_rows)
    tzn = recipient_tz_name(win, rec)
    if not within_window_now(win, tzn, now):
        причины[f"час получателя закрыт (tz={tzn})"] += 1
        примеры.setdefault(f"час получателя закрыт (tz={tzn})", r["id"])
        continue
    mid = snd.pick_mailbox(rec, camp, now=now, message=m)
    if mid:
        причины["ГОТОВО К ОТПРАВКЕ"] += 1
        примеры.setdefault("ГОТОВО К ОТПРАВКЕ", r["id"])
        continue
    # разбираем, почему пусто
    pool = snd._route_pool(rec, camp)
    ящики = пулы.get(pool or "", [])
    блок = Counter()
    for mb in ящики:
        d = snd.division_block(rec, mb, message=m)
        if d is not None:
            блок["чужое направление"] += 1
            continue
        if not snd.can_send_now(mb, now=now):
            блок["ящик не может слать сейчас"] += 1
            continue
        блок["годен"] += 1
    ключ = f"нет ящика | пул={pool} ({len(ящики)} шт) {dict(блок)}"
    причины[ключ] += 1
    примеры.setdefault(ключ, r["id"])

print("\n== вердикт по каждому ждущему письму ==")
for k, v in причины.most_common():
    print(f"  {v:>5}  {k}   (пример #{примеры.get(k)})")

print("\n== состояние мейеровских ящиков ==")
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    if "meyer" not in div and "мейер" not in div:
        continue
    st = store.get_mailbox_state(mb.mailbox_id)
    день = getattr(st, "sent_today", 0) if st else 0
    рд = getattr(st, "ramp_day", 0) if st else 0
    посл = getattr(st, "last_sent_at", None) if st else None
    лим = snd._daily_limit(mb.provider, рд, mb.mailbox_id)
    гейт = snd.gates.check_mailbox(mb.mailbox_id)
    пулы_мб = [p for p, lst in пулы.items() if mb.mailbox_id in lst]
    print(f"  {mb.mailbox_id:<38} рамп{рд:>3} {день:>3}/{лим:<3} "
          f"пауза={getattr(st,'paused',False)} гейт={гейт.tripped} "
          f"посл={str(посл)[:16]} пулы={пулы_мб}")

print("\n== глобальный гейт ==")
print("  ", snd.gates.check_global().tripped)
