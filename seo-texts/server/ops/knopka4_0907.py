# -*- coding: utf-8 -*-
"""Только чтение: вызовы Sender.send_reply в веб-панели."""
import io
import os
import re

for корень in (r"C:\sender\server", r"C:\sender\web"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            низ = ф.lower()
            if not ф.endswith(".py") or "agent" in низ or "runner" in низ:
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if "send_reply(" not in т:
                continue
            for м in re.finditer(r"send_reply\(", т):
                нач = max(т.rfind("\n@", 0, м.start()),
                          т.rfind("\ndef ", 0, м.start()),
                          т.rfind("\nasync def ", 0, м.start()))
                нач = нач if нач > 0 else max(0, м.start() - 2400)
                кусок = т[нач:м.start() + 600]
                print("\n" + "=" * 12 + " %s " % п.replace(r"C:\sender", "")
                      + "=" * 12)
                print(кусок[-3000:])
