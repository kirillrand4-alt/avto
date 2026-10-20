# -*- coding: utf-8 -*-
"""Кампании: пул, конфиг и направление по campaign_division."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.company_card import campaign_division  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db")
for (cid,) in c.execute("SELECT id FROM campaigns ORDER BY id"):
    к = st.get_campaign(cid)
    print(cid, getattr(к, "name", None), "| пул", getattr(к, "provider_pool", None), "| конфиг", getattr(к, "config", None) or getattr(к, "config_json", None), "| направление:", campaign_division(к))
