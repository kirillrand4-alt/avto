# -*- coding: utf-8 -*-
"""Почему письмо КЦ не берёт ящик: pick_mailbox на живом отправителе по 3 письмам кампании 15."""
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
d = build_deps(cfg, st, dry_run=True)
сн = d.confirm._sender
print("pool_kc в конфиге:", len(cfg.provider_pools().get("pool_kc", [])), "routing:", cfg.get("provider_split.routing", {}))
c = sqlite3.connect(r"C:\sender\sender.db")
now = datetime.now(timezone.utc)
for (mid,) in c.execute("SELECT id FROM messages WHERE campaign_id=15 AND status='scheduled' LIMIT 3").fetchall():
    m = st.get_message(mid) if hasattr(st, "get_message") else None
    r = st.get_recipient(m.recipient_id)
    k = st.get_campaign(15)
    print("msg", mid, r.email, "mx:", r.mx_provider, "кампания пул:", k.provider_pool, "маршрут:", сн._route_pool(r, k))
    print("   pick:", сн.pick_mailbox(r, k, now=now, message=m))
    for mb in cfg.provider_pools().get("pool_kc", [])[:3]:
        print("   ", mb, "division_block:", сн.division_block(r, mb, message=m), "can_send:", сн.can_send_now(mb, now=now))
print("=== KC PICK ===")
