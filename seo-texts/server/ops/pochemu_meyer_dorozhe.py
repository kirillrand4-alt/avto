# -*- coding: utf-8 -*-
"""Почему перезапись Meyer вышла дороже генерации КЦ.

Замер: 60 попыток, $41.41 по счётчику - $0.69 за попытку против $0.12 у
компрессорных писем. Разница пятикратная, и объяснять её надо настройками,
а не ощущением.
"""
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
for ключ in ("ai_quota.model", "ai_quota.checker_model", "ai_quota.best_of",
             "ai_quota.rounds", "ai_letter.model", "ai_letter.best_of"):
    try:
        print(f"  {ключ}: {cfg.get(ключ)!r}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  {ключ}: нет в конфиге ({type(ex).__name__})")
print("\n  секция ai_quota целиком:")
try:
    print("   ", cfg.get("ai_quota"))
except Exception as ex:                                          # noqa: BLE001
    print("    нет секции:", type(ex).__name__)
for пер in ("GEN_CHECKER_MODEL", "GEN_BEST_OF", "AI_LETTER_MODEL",
            "AI_LETTER_TEH_LENS", "PROVIDER_MODEL"):
    print(f"  env {пер}: {os.environ.get(пер)!r}")
