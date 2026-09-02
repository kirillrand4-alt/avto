# -*- coding: utf-8 -*-
"""Только чтение: код заслона «уже писали» и есть ли у него окно/тумблер."""
import io
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
н = next(i for i, л in enumerate(лн) if "УЖЕ ПИСАЛИ ЭТОМУ АДРЕСУ" in л)
for i in range(н, min(н + 52, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:106]))

cfg = Config.load(r"C:\sender\sender.yaml")
print("\n=== ВОЗМОЖНЫЕ НАСТРОЙКИ ===")
for к in ("auto_send.povtor_dney", "auto_send.repeat_days", "confirm.svezhiy_kontakt",
          "guard.days", "confirm.guard_days", "auto_send.guard_days"):
    print("  %-28s %s" % (к, cfg.get(к, "нет ключа")))
