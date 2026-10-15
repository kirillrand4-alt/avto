# -*- coding: utf-8 -*-
"""Какой ящик панель даст карточке: yashchik_dlya_kartochki.py <review_id> [<review_id>...]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
cs = build_deps(cfg, Store(cfg.get("service.db_path", r"C:\sender\sender.db")), dry_run=True).confirm
for rid in map(int, sys.argv[1:]):
    с = cs.get(rid)
    к = cs.send_as(с, prefer_division=cs.letter_division(с))
    print("#%d %s письмо %s -> ящик %s (%s) %s" % (rid, с.get("email"), cs.letter_division(с), к.get("mailbox_id"),
                                                к.get("division"), к.get("note") or ""))
print("=== ЯЩИК КАРТОЧКИ ===")
