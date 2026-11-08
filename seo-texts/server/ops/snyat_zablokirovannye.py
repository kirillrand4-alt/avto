# -*- coding: utf-8 -*-
"""Владелец 08.11: снять из «Подтвердить отправку» карточки, которые кнопка «в автоотправку» не
пропускает: сделка КЦ в работе (гейт направлений «СДЕЛКА»), недавнее письмо (recent_contact),
лимит писем на компанию (company_quota). Остальные блоки не трогаем. [--primenit]"""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender"); sys.path.insert(1, r"C:\sender\sender")
from sender.config import Config        # noqa: E402
from sender.store import Store          # noqa: E402
from sender.wiring import build_deps    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
к = store._conn
снять, сч = [], Counter()
for r in cs.pending(limit=100_000):
    if (r.get("kind") or "outbound") == "reply": continue
    причина = None
    try:
        б = cs._guard(inn=r.get("inn"), email=r.get("email") or "")
        if б and ("recent_contact" in str(б) or "company_quota" in str(б)): причина = str(б)[:60]
    except Exception:  # noqa: BLE001
        pass
    if not причина:
        try:
            д = cs._division_blocked(r)
            if д and "СДЕЛКА" in str(д): причина = str(д)[:60]
        except Exception:  # noqa: BLE001
            pass
    if причина:
        снять.append((int(r["id"]), r.get("message_id"), причина)); сч[причина.split(":")[0][:30]] += 1
print("к снятию:", len(снять), dict(сч))
if "--primenit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    with store._lock:
        for kid, mid, п in снять:
            к.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", ("владелец 08.11 снять: " + п, т, т, kid))
            if mid: к.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='pending_review'", ("снято: " + п, т, mid))
        к.commit()
    print("снято")
