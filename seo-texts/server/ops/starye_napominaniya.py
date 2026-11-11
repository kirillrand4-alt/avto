# -*- coding: utf-8 -*-
"""Висящие напоминания по дате создания × ящику × паузе ящика; почему старые не уходят. Только чтение."""
import json, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
пауза = {m.mailbox_id: bool(getattr(st.get_mailbox_state(m.mailbox_id), "paused", False)) for m in cfg.mailboxes()}
напр = {m.mailbox_id: str(getattr(m, "division", "")) for m in cfg.mailboxes()}
сч = Counter()
for cr, pj in st._conn.execute("SELECT substr(created_at,1,10), panel_json FROM confirm_reviews WHERE status='pending' AND kind='reply' AND panel_json LIKE '%napominanie%'"):
    mb = json.loads(pj or "{}").get("mailbox_id")
    сч[(cr if cr < "2026-11-09" else "09–10.11", mb if cr < "2026-11-09" else "-", "пауза" if пауза.get(mb) else ("нет в конфиге" if mb not in пауза else напр.get(mb)))] += 1
for k, n in sorted(сч.items()): print("%4d" % n, k)
