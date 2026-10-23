# -*- coding: utf-8 -*-
"""Пауза / снятие паузы со всех ящиков направления (владелец 23.10:
«притормозим пока КЦ, тогда Meyer уйдёт нормально»). Причина пишется в
pause_reason; снимаем только ту паузу, что поставлена этим скриптом (чужие
паузы — спам-гейт, ручные — не трогаем).
    pauza_napravleniya.py <kc|meyer> --pauza | --snyat"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

нап = sys.argv[1]
ПРИЧИНА = "владелец 23.10: притормозить %s, пропустить другое направление" % нап
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
n = 0
for mb in cfg.mailboxes():
    if mb.division != нап:
        continue
    s = st.get_mailbox_state(mb.mailbox_id)
    if "--pauza" in sys.argv and not getattr(s, "paused", False):
        st.set_mailbox_paused(mb.mailbox_id, True, ПРИЧИНА)
        n += 1
    elif "--snyat" in sys.argv and getattr(s, "paused", False) and str(getattr(s, "pause_reason", "")).startswith("владелец 23.10: притормозить"):
        st.set_mailbox_paused(mb.mailbox_id, False, None)
        n += 1
print("%s: изменено ящиков %d" % ("пауза" if "--pauza" in sys.argv else "снято", n))
