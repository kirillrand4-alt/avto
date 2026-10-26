# -*- coding: utf-8 -*-
"""Почему КЦ не уходит: время в очереди, последние отправки и лимиты ящиков КЦ, ошибки. Только чтение."""
import json
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
кц = [k for k, v in кам.items() if "meyer" not in str(v).lower()]
q = ",".join(map(str, кц))
print("КЦ scheduled: мин/макс времени:", c.execute("SELECT MIN(scheduled_at), MAX(scheduled_at), COUNT(*) FROM messages WHERE status='scheduled' AND campaign_id IN (%s)" % q).fetchone())
print("КЦ наступивших:", c.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled' AND scheduled_at<=strftime('%%Y-%%m-%%dT%%H:%%M:%%S','now') AND campaign_id IN (%s)" % q).fetchone())
сл = st.get_setting("send_limits") or {}
if isinstance(сл, str):
    сл = json.loads(сл)
пм = сл.get("per_mailbox") or {}
сч = Counter()
for mb in cfg.mailboxes():
    if mb.division != "kc":
        continue
    s = st.get_mailbox_state(mb.mailbox_id)
    у = int(getattr(s, "sent_today", 0) or 0) if s and str(getattr(s, "day_key", "")) == "2026-10-26" else 0
    сч["упёрся в лимит" if у >= int(пм.get(mb.mailbox_id) or 40) else "есть место"] += 1
print("ящики КЦ:", dict(сч), "| пример лимита:", list(пм.items())[:2])
print("последние КЦ-отправки:", c.execute("SELECT MAX(sent_at) FROM messages WHERE status='sent' AND campaign_id IN (%s)" % q).fetchone())
print("ошибки КЦ за 2 часа:", Counter((r[0] or "")[:70] for r in c.execute(
    "SELECT last_error FROM messages WHERE campaign_id IN (%s) AND updated_at >= datetime('now','-2 hours') AND status IN ('failed','skipped')" % q)).most_common(8))
print("гейт направлений/спам-гейт:", st.get_setting("division_gate") or "", st.get_setting("spam_gate") or "")
