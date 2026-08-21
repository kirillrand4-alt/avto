# -*- coding: utf-8 -*-
"""Расшифровать экран «Ёмкость пулов» и строку ожидания над ним.

Числа берём из тех же мест, что панель: пулы - config.provider_pools(),
ёмкость - Sender.mailbox_readiness (рамп-день плюс ручной потолок),
ожидание - таблица messages, подтверждение - confirm_reviews.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards                        # noqa: E402
from sender.config import Config                                    # noqa: E402
from sender.gates import Gates                                      # noqa: E402
from sender.sender import Sender                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.suppression import Suppression                          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))

напр_ящика = {}
for mb in cfg.mailboxes():
    d = str(getattr(mb, "division", "") or "").lower()
    напр_ящика[mb.mailbox_id] = "Meyer" if ("meyer" in d or "мейер" in d) \
        else "КЦ"

пулы = cfg.provider_pools()
все_ящики = set()
print("ПУЛЫ\n")
for имя, ids in пулы.items():
    ёмк = 0
    сч = Counter()
    for mid in ids:
        try:
            r = snd.mailbox_readiness(mid)
        except Exception:                                          # noqa: BLE001
            continue
        if "no_state" in (r.reasons or ()):
            continue
        ёмк += int(r.daily_limit)
        сч[напр_ящика.get(mid, "?")] += 1
        все_ящики.add(mid)
    print(f"  {имя:<16} ящиков {len(ids):>3}  ёмкость {ёмк:>4}  "
          f"направления: {dict(сч)}")
print(f"\n  РАЗНЫХ ящиков во всех пулах вместе: {len(все_ящики)}")
пересечения = {}
имена = list(пулы)
for i, a in enumerate(имена):
    for b in имена[i + 1:]:
        общее = set(пулы[a]) & set(пулы[b])
        if общее:
            пересечения[f"{a} ∩ {b}"] = len(общее)
print(f"  пересечения пулов: {пересечения or 'нет'}")

сейчас = datetime.now(timezone.utc).isoformat()
with store._lock:
    ждут = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending')"
    ).fetchone()[0]
    просроч = store._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','sending') "
        "AND scheduled_at < ?", (сейчас,)).fetchone()[0]
    подтв = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'"
    ).fetchone()[0]
    по_виду = store._conn.execute(
        "SELECT COALESCE(kind,'outbound'), COUNT(*) FROM confirm_reviews "
        " WHERE status='pending' GROUP BY 1").fetchall()
    по_камп = store._conn.execute(
        "SELECT campaign_id, COUNT(*) FROM confirm_reviews "
        " WHERE status='pending' GROUP BY 1 ORDER BY 2 DESC").fetchall()

print(f"\nОЖИДАНИЕ\n  ждут отправки (scheduled+sending): {ждут}")
print(f"    из них просрочено (слот в прошлом): {просроч}")
print(f"    на будущее: {ждут - просроч}")
print(f"  ждут подтверждения (pending): {подтв}")
print(f"    по виду: {dict(по_виду)}")
print(f"    по кампаниям: {dict(по_камп)}")
