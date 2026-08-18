# -*- coding: utf-8 -*-
"""Расшить голову очереди: непроходимые сейчас письма — на следующий слот.

Цикл берёт партию из десяти писем по возрасту. Если все десять адресованы
в пул, где сейчас нет ни одного пригодного ящика (у нас это mail.ru: четыре
ящика под гейтом репутации, два выбрали дневной лимит), он их возвращает и
проход заканчивает. Письма, стоящие следом и полностью готовые к отправке,
он не видит вообще — очередь стоит при живых ящиках.

Здесь двигаем ТОЛЬКО те письма, которые сейчас всё равно уйти не могут:
пул пуст. Новый слот считаем той же функцией, которой пользуется цикл
(next_slot по времени получателя) — то есть завтрашним утром получателя.
Ни одно проходимое письмо не трогаем.

Настоящее лечение — в коде цикла (проход обязан идти дальше по очереди);
это разбор затора здесь и сейчас.

    python zapusk_svoego_skripta.py ops/rasshit_golovu_ocheredi.py
    python zapusk_svoego_skripta.py ops/rasshit_golovu_ocheredi.py --двигать
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,        # noqa: E402
                              window_from, within_window_now)
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.wiring import build_deps                               # noqa: E402

ДВИГАТЬ = "--двигать" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd = deps.live_sender or deps.sender
сейчас = datetime.now(timezone.utc)
win = window_from(store, cfg)

with store._lock:
    ряд = store._conn.execute(
        """SELECT m.id, m.recipient_id, m.campaign_id FROM messages m
            WHERE m.status='scheduled' AND m.scheduled_at <= ?
              AND (SELECT cr.status FROM confirm_reviews cr
                    WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1)
                  IN ('approved','edited')
            ORDER BY m.scheduled_at, m.id""", (сейчас.isoformat(),)).fetchall()

двигаем, остаются = [], 0
for mid, rid, cid in ряд:
    r = store.get_recipient(int(rid))
    камп = store.get_campaign(int(cid))
    if r is None or камп is None:
        continue
    tz = recipient_tz_name(win, r)
    if not within_window_now(win, tz, сейчас):
        continue                      # вне окна — цикл сам подвинет

    class _M:
        id = mid
    if snd.pick_mailbox(r, камп, now=сейчас, message=_M()):
        остаются += 1
        continue
    двигаем.append((mid, r.email, next_slot(win, tz, сейчас)))

print(f"писем, чей срок настал: {len(ряд)}")
print(f"  уйдут прямо сейчас (не трогаем): {остаются}")
print(f"  некуда слать, двигаем на следующий слот: {len(двигаем)}")
по_слотам = Counter(str(с)[:16] for _i, _e, с in двигаем)
for с, n in sorted(по_слотам.items()):
    print(f"    -> {с} UTC: {n}")
for mid, email, с in двигаем[:5]:
    print(f"    напр. #{mid} {email} -> {str(с)[:16]}")

if not ДВИГАТЬ:
    print("\nсухой прогон: очередь не тронута. Двигать — аргумент --двигать")
    raise SystemExit(0)

сдвинуто = 0
for mid, _e, слот in двигаем:
    try:
        store.reschedule_message(int(mid), слот)
        сдвинуто += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{mid}: {str(ex)[:100]}")
print(f"\nсдвинуто писем: {сдвинуто}")
with store._lock:
    n = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status='scheduled' "
        "AND scheduled_at<=?", (сейчас.isoformat(),)).fetchone()[0]
print(f"осталось «срок настал»: {n} — теперь в голове очереди отправимые")
