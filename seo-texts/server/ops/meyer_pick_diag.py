# -*- coding: utf-8 -*-
"""Почему отправщик не берёт письма Meyer: для наступивших писем кампаний
Meyer — pick_mailbox штатным кодом (dry_run, без отправки) и гейт направления
по каждому ящику Meyer. Только чтение, ничего не шлёт."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, st, dry_run=True)
snd = deps.confirm._sender
print("sender:", type(snd).__name__, "| методы:", [m for m in dir(snd) if not m.startswith("__") and ("mailbox" in m or "window" in m or "limit" in m)])
now = datetime.now(timezone.utc)
меер = [mb.mailbox_id for mb in cfg.mailboxes() if mb.division == "meyer"]
for mb in меер:
    try:
        print("  %-38s can_send_now=%s | readiness=%s" % (mb, snd.can_send_now(mb, now=now) if hasattr(snd, "can_send_now") else "?",
              str(snd.mailbox_readiness(mb))[:250] if hasattr(snd, "mailbox_readiness") else "?"))
    except Exception as ex:  # noqa: BLE001
        print("  %s: %r" % (mb, ex))
ids = [r[0] for r in st._conn.execute("SELECT id FROM messages WHERE campaign_id IN (13,14,18) AND status='scheduled' "
                                      "AND scheduled_at<=? ORDER BY scheduled_at LIMIT 4", (now.strftime("%Y-%m-%dT%H:%M:%S"),))]
for mid in ids:
    m = st.get_message(mid) if hasattr(st, "get_message") else None
    rid, cid = st._conn.execute("SELECT recipient_id, campaign_id FROM messages WHERE id=?", (mid,)).fetchone()
    rec, camp = st.get_recipient(rid), st.get_campaign(cid)
    print("\n#%d кампания %s | %s | tz %s" % (mid, cid, rec.email, getattr(rec, "tz", None)))
    try:
        print("   pick_mailbox:", snd.pick_mailbox(rec, camp, now=now, message=m))
    except Exception as ex:  # noqa: BLE001
        print("   pick_mailbox упал:", repr(ex)[:300])
    for mb in меер[:4]:
        try:
            print("   %-38s division_block=%s" % (mb, snd.division_block(rec, mb, message=m)))
        except Exception as ex:  # noqa: BLE001
            print("   %s: %r" % (mb, ex))
    for имя in ("explain_pick", "why_no_mailbox", "_pick_reasons", "pick_reasons"):
        if hasattr(snd, имя):
            try:
                print("   %s:" % имя, getattr(snd, имя)(rec, camp, now=now))
            except Exception as ex:  # noqa: BLE001
                print("   %s упал: %r" % (имя, ex))
