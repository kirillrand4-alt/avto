# -*- coding: utf-8 -*-
"""Только чтение: размер партии за проход."""
import io
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
н = next(i for i, л in enumerate(лн) if "def __init__" in л)
for i in range(н, min(н + 30, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))
cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("auto_send.batch", "auto_send.interval", "orchestrator.send_batch"):
    print("  конфиг %-26s %s" % (к, cfg.get(к, "нет ключа")))
