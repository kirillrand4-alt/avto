# -*- coding: utf-8 -*-
"""Ручные ответы, застрявшие в очереди (владелец 22.10: «отправь мой ответ…
ещё несколько я писал»): карточки kind=reply не отправленные + карточки за
сегодня с decided_by оператора без отправки; ящик треда и его пауза. Только чтение."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db")
for r in c.execute("SELECT id, kind, status, email, subject, created_at, decided_by, reason, substr(panel_json,1,4000) FROM confirm_reviews "
                   "WHERE (kind='reply' AND status NOT IN ('sent','skipped')) OR (created_at>='2026-10-22' AND kind='reply') ORDER BY id"):
    import json
    try:
        pj = json.loads(r[8] + ("" if r[8].endswith("}") else "}")) if r[8] else {}
    except Exception:  # noqa: BLE001
        pj = {}
    mb = None
    for k in ("mailbox_id", "send_as", "mailbox"):
        mb = mb or (pj.get(k) if isinstance(pj, dict) else None)
    # ящик, на который клиент ответил — из последнего письма этому адресу
    п = c.execute("SELECT m.mailbox_id FROM messages m JOIN recipients rr ON rr.id=m.recipient_id WHERE lower(rr.email)=lower(?) "
                  "AND m.status='sent' ORDER BY m.sent_at DESC LIMIT 1", (r[3],)).fetchone()
    ящ = mb or (п[0] if п else None)
    s = st.get_mailbox_state(ящ) if ящ else None
    print("#%s %s %s | %s | %s | создан %s | решал %s | %s | ящик %s пауза=%s" % (
        r[0], r[1], r[2], r[3], str(r[4])[:50], r[5][:16], r[6], str(r[7])[:60], ящ, getattr(s, "paused", None)))
