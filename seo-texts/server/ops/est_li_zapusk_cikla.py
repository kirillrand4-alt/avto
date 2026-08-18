# -*- coding: utf-8 -*-
"""Есть ли в боевом api/app.py запуск цикла автоотправки (и та ли это версия)."""
import hashlib
import io

путь = r"C:\sender\sender\api\app.py"
b = io.open(путь, "rb").read()
т = b.decode("utf-8", "replace")
print(f"{путь}: {len(b)} байт sha256={hashlib.sha256(b).hexdigest()}")
for фраза in ("_auto_send.start()", "AutoSendLoop(", "app.state.auto_send",
              "if _auto_send.sender is not None", "live_sender"):
    print(f"  {фраза!r}: {т.count(фраза)}")
строки = т.splitlines()
for i, s in enumerate(строки):
    if "AutoSendLoop(" in s or "_auto_send.start()" in s:
        for j in range(max(0, i - 3), min(len(строки), i + 4)):
            print(f"  {j + 1:>5}| {строки[j][:120]}")
        print("  ---")
