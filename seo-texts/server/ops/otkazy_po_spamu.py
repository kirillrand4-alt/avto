# -*- coding: utf-8 -*-
"""Отказы «подозрение на спам» за сутки и сработал ли заслон."""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.otkaz_spam import (porogi, min_yashchikov,          # noqa: E402
                               nachalo_sutok, СОБЫТИЕ)
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
п_ящик, п_напр = porogi(cfg)
мин_ящ = min_yashchikov(cfg)
теперь = datetime.now(timezone.utc)

с_ящика = Counter()
по_часам = Counter()
ушло_по_часам = Counter()
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at", "occurred_at") if c in кол), None)
    тп = next((c for c in ("type", "kind", "event_type") if c in кол), None)
    ящ = next((c for c in ("mailbox_id", "mailbox") if c in кол), None)
    for р in store._conn.execute(
            "SELECT * FROM events WHERE %s=? AND %s >= datetime('now','-1 day')"
            % (тп, вр), (СОБЫТИЕ,)):
        с_ящика[str(р[ящ] or "?") if ящ else "?"] += 1
        по_часам[str(р[вр])[:13]] += 1
    for р in store._conn.execute(
            "SELECT %s t FROM events WHERE %s='sent' AND %s >= "
            "datetime('now','-1 day')" % (вр, тп, вр)):
        ушло_по_часам[str(р["t"])[:13]] += 1

print("--- по часам (UTC): отправлено / отказов ---")
for к in sorted(set(list(по_часам) + list(ушло_по_часам)))[-14:]:
    у, о = ушло_по_часам.get(к, 0), по_часам.get(к, 0)
    доля = (100.0 * о / (у + о)) if (у + о) else 0
    print("   %s  ушло %4d  отказов %3d  (%.0f%%)" % (к, у, о, доля))
print("")
print("--- отказы по ящикам за сутки ---")
for к, в in с_ящика.most_common(12):
    print("   %-42s %3d %s" % (к[:42], в, "← выше порога" if в >= п_ящик else ""))

пауз = []
for mb in cfg.mailboxes():
    st = store.get_mailbox_state(mb.mailbox_id)
    if st is not None and getattr(st, "paused", False):
        пауз.append((mb.mailbox_id, str(getattr(st, "pause_reason", "") or "")))
print("")
print("=" * 74)
print("=== ЗАСЛОН ПО ОТКАЗАМ ===")
print("порог ящика: %s; порог направления: %s; мин. разных ящиков: %s"
      % (п_ящик or "ВЫКЛ", п_напр or "ВЫКЛ", мин_ящ))
print("отказов за сутки всего: %d, разных ящиков: %d"
      % (sum(с_ящика.values()), len(с_ящика)))
print("ящиков на паузе: %d" % len(пауз))
for i, r in пауз:
    print("   %-40s %s" % (i[:40], r[:60]))
