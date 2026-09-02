# -*- coding: utf-8 -*-
"""Только чтение: как устроен start() цикла и что будет от тумблера."""
import io

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
нач = next(i for i, л in enumerate(лн) if л.startswith("class AutoSendLoop"))
for i in range(нач, min(нач + 62, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))
