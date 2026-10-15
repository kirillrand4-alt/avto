# -*- coding: utf-8 -*-
"""Почему ящики опыта не шлют: can_send_now, гейт, пауза, пейсинг, окно; срок писем опыта."""
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сн = build_deps(cfg, st, dry_run=True).confirm._sender
now = datetime.now(timezone.utc)
print("сейчас", now.isoformat()[:19], "в окне:", сн._within_window(now))
for я in ["vladislav.melnikov", "i.lyapin", "balakirev.a", "a.dmitriev", "kirchatov.n"]:
    м = я + "@compressor-pro-systems.ru"
    s = st.get_mailbox_state(м)
    г = сн.gates.check_mailbox(м)
    print("%-45s can=%s manual=%s пауза=%s гейт=%s %s посл=%s" % (м, сн.can_send_now(м, now=now), сн.can_send_now(м, now=now, manual=True),
          getattr(s, "paused", None), г.tripped, getattr(г, "reason", ""), str(getattr(s, "last_sent_at", ""))[:19]))
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT id, status, scheduled_at, mailbox_id, claimed_at FROM messages WHERE mailbox_id LIKE '%compressor-pro-systems%' AND status IN ('scheduled','sending')").fetchall())
print("=== ОПЫТ ЯЩИКИ ===")
