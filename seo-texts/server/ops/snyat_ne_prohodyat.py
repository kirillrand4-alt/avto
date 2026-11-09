# -*- coding: utf-8 -*-
"""Владелец 09.11: «24 письма если упираются в проверки — давай уберём». Снимает из «Подтвердить
отправку» обычные (не reply) карточки, которые кнопка «В автоотправку» не пропускает (та же цепочка,
что verhushka_knopki: удержание / заслон / направления). Плюс печатает настоящие ответы клиентам
в очереди (reply без напоминаний). [--primenit]"""
import re, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store), cards=CompanyCards(index_path=r"C:\sender\obzvon-index.db", enrich_db_path=r"C:\sender\enrich.db"))
к = store._conn
снять, сч = [], Counter()
for r in cs.pending(limit=100_000):
    if (r.get("kind") or "outbound") == "reply":
        пj = (к.execute("SELECT COALESCE(panel_json,'') FROM confirm_reviews WHERE id=?", (r["id"],)).fetchone() or [""])[0]
        if "napominanie" not in пj and "заходы" not in пj:
            тело = (к.execute("SELECT substr(body,1,400), subject, created_at FROM confirm_reviews WHERE id=?", (r["id"],)).fetchone())
            print("ОТВЕТ #%s %s ИНН %s | %s | %s\n    %s" % (r["id"], r.get("email"), r.get("inn"), тело[2][:16], тело[1], (тело[0] or "").replace("\n", " / ")))
        continue
    п = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    if ((п or {}).get("actions") or {}).get("confirm_hold"):
        причина = "удержание: " + ",".join(sorted(str(f.get("code")) for f in (п.get("stop_flags") or [])))
    else:
        bl = cs._guard(inn=r.get("inn"), email=r.get("email") or "")
        dv = None if bl else cs._division_blocked(r)
        причина = ("заслон: " + str(bl)) if bl else (("направления: " + str(dv)) if dv else None)
    if причина:
        снять.append((int(r["id"]), r.get("message_id"), причина[:80])); сч[re.sub(r"\d+", "N", причина)[:45]] += 1
print("к снятию:", len(снять)); [print("  %3d  %s" % (n, k)) for k, n in сч.most_common()]
if "--primenit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    with store._lock:
        for kid, mid, п in снять:
            к.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", ("владелец 09.11 снять (не проходит в автоотправку): " + п, т, т, kid))
            if mid: к.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='pending_review'", ("снято: " + п[:60], т, mid))
        к.commit()
    print("снято", len(снять))
