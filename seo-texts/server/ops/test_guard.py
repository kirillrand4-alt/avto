# -*- coding: utf-8 -*-
"""Проверка заслона ConfirmSend._guard на адресах: test_guard.py <адрес>,<адрес>"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.confirm import ConfirmSend      # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, st, Suppression(st))
for em in sys.argv[1].split(","):
    r = st._conn.execute("SELECT inn, extra_json FROM recipients WHERE lower(email)=?", (em,)).fetchone()
    inn = r[0] if r else None
    last = st.last_contact(email=em)
    print(em, "| ИНН", inn, "| last_contact:", (last or {}).get("ts"), (last or {}).get("campaign_id"),
          "| _recent_contact:", bool(cs._recent_contact(email=em)),
          "| povtor_razreshen:", cs._povtor_razreshen(em, last) if last else None,
          "| guard:", cs._guard(inn=inn, email=em))
