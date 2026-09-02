# -*- coding: utf-8 -*-
"""Только чтение: тумблер «слать вне базы» и хвост division_block."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
import sender.sender as S         # noqa: E402

исх = inspect.getsource(S.Sender.division_block)
н = исх.find("ИНН не из базы обзвона")
print("=== ХВОСТ division_block ===")
print(исх[н - 100:н + 1900])

cfg = Config.load(r"C:\sender\sender.yaml")
print("\n=== ЗНАЧЕНИЯ ТУМБЛЕРОВ СЕЙЧАС ===")
for к in ("obzvon.vne_bazy", "confirm.vne_bazy", "gates.vne_bazy",
          "send_outside_base", "obzvon.allow_outside", "confirm.slat_vne_bazy",
          "flags.vne_bazy", "policy.vne_bazy"):
    зн = cfg.get(к, "НЕТ КЛЮЧА")
    print("  %-26s %s" % (к, зн))
