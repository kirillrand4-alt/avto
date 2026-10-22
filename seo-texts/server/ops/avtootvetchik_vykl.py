# -*- coding: utf-8 -*-
"""Выключить робота-черновики ответов (владелец 22.10: «робот раньше не писал
ответы, только сейчас начал — отключи»). Тумблер панели autoresponder_enabled
= false: ReplyPipeline спрашивает его на КАЖДОМ входящем, перезапуск не нужен.
Уже готовые черновики не трогаем. Плюс история: карточки kind=reply по дням
(кто решал) — когда робот начал. --vkl — включить обратно.
    avtootvetchik_vykl.py [--primenit | --vkl]"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("сейчас тумблер:", st.get_setting("autoresponder_enabled", None), "| конфиг autoresponder.enabled:",
      cfg.get("autoresponder.enabled", None))
c = sqlite3.connect(r"C:\sender\sender.db")
for r in c.execute("SELECT substr(created_at,1,10), status, COALESCE(decided_by,'—'), COUNT(*) FROM confirm_reviews "
                   "WHERE kind='reply' AND created_at>='2026-10-01' GROUP BY 1,2,3 ORDER BY 1"):
    print("  ", r)
if "--vkl" in sys.argv:
    st.set_setting("autoresponder_enabled", True)
    print("=== РОБОТ-ЧЕРНОВИКИ: ВКЛЮЧЕН ===")
elif "--primenit" in sys.argv:
    st.set_setting("autoresponder_enabled", False)
    print("=== РОБОТ-ЧЕРНОВИКИ: ВЫКЛЮЧЕН, тумблер теперь", st.get_setting("autoresponder_enabled", None), "===")
